import tree_sitter_python as _ts_python
from tree_sitter import Language

from app.ingestion.source_text import node_text

QUERY = """
(function_definition
  name: (identifier) @func.name
  parameters: (parameters) @func.params
) @func.def

(class_definition
  name: (identifier) @class.name
) @class.def

(import_statement
  name: (dotted_name) @import.module @import.bound_name
) @import.stmt

(import_statement
  name: (aliased_import
    name: (dotted_name) @import.module @import.bound_name
    alias: (identifier) @import.alias
  )
) @import.stmt

(import_from_statement
  module_name: (dotted_name) @import.module
  name: (dotted_name) @import.bound_name
) @import.stmt

(import_from_statement
  module_name: (dotted_name) @import.module
  name: (aliased_import
    name: (dotted_name) @import.bound_name
    alias: (identifier) @import.alias
  )
) @import.stmt

(import_from_statement
  module_name: (relative_import) @import.relmodule
  name: (dotted_name) @import.bound_name
) @import.stmt

(import_from_statement
  module_name: (relative_import) @import.relmodule
  name: (aliased_import
    name: (dotted_name) @import.bound_name
    alias: (identifier) @import.alias
  )
) @import.stmt

(import_from_statement
  module_name: (dotted_name) @import.module
  (wildcard_import) @import.wildcard
) @import.stmt

(import_from_statement
  module_name: (relative_import) @import.relmodule
  (wildcard_import) @import.wildcard
) @import.stmt
"""
REF_QUERY = """
(call
  function: (identifier) @reference.call
)

(call
  function: (attribute
    object: (_) @reference.call.object
    attribute: (identifier) @reference.call.attr
  )
)

(class_definition
  superclasses: (argument_list
    (identifier) @reference.base_class
  )
)
"""

CLASS_NODE_TYPES = {"class_definition"}
FILE_EXTENSION = ".py"


def get_language() -> Language:
    return Language(_ts_python.language())

def _unwrap_to_function_definition(node):
    """If node is a decorated_definition wrapping a function, return the inner
    function_definition node. Returns the node itself if it's already a bare
    function_definition, or None if neither applies."""
    if node.type == "decorated_definition":
        return node.child_by_field_name("definition")
    return node if node.type == "function_definition" else None


def get_definition_name(node, content: bytes) -> str:
    """Pull the identifier name out of a (possibly decorator-wrapped) definition node."""
    target = _unwrap_to_function_definition(node) or node
    name_node = target.child_by_field_name("name")
    if name_node is None:
        return "<anonymous>"
    return node_text(name_node, content)


def unwrap_decorated_definition_node(def_node):
    """Unwrap to the decorated_definition parent, if present, so decorators aren't lost."""
    if def_node.parent is not None and def_node.parent.type == "decorated_definition":
        return def_node.parent
    return def_node


def get_enclosing_class_name(def_node, captures: dict, content: bytes) -> str | None:
    """Return the owning class name for Python methods."""
    parent = def_node.parent
    if parent is not None and parent.type == "block":
        grandparent = parent.parent
        if grandparent is not None and grandparent.type == "class_definition":
            name_node = grandparent.child_by_field_name("name")
            if name_node is not None:
                return node_text(name_node, content)
    return None

def get_namespace(def_node, captures: dict, content: bytes) -> list[str]:
    """Walk up the AST and return the full namespace path (classes and functions)."""
    namespace = []
    current = def_node.parent
    while current is not None:
        if current.type in ("class_definition", "function_definition"):
            name_node = current.child_by_field_name("name")
            if name_node is not None:
                namespace.append(node_text(name_node, content))
        current = current.parent
    return list(reversed(namespace))


def get_class_member_stub_info(node, content: bytes):
    """For class-skeleton building: identify a method node and its stub signature."""
    function_node = _unwrap_to_function_definition(node)
    if function_node is None:
        return None

    decorators: list[str] = []
    if node.type == "decorated_definition":
        decorators = [
            node_text(child, content)
            for child in node.children
            if child.type == "decorator"
        ]

    name = node_text(function_node.child_by_field_name("name"), content)
    params = node_text(function_node.child_by_field_name("parameters"), content)
    prefix = "async def" if any(child.type == "async" for child in function_node.children) else "def"

    return {"name": name, "params": params, "decorators": decorators, "prefix": prefix}

def get_class_skeleton_header(name: str) -> str:
    return f"class {name}:"

def get_class_skeleton_footer() -> str | None:
    return None

def get_module_index_filename() -> str | None:
    return "__init__.py"