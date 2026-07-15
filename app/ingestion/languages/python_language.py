QUERY = """
(function_definition
  name: (identifier) @func.name
  parameters: (parameters) @func.params
) @func.def

(class_definition
  name: (identifier) @class.name
) @class.def

(import_statement
  name: (dotted_name) @import.module
) @import.stmt

(import_statement
  name: (aliased_import
    name: (dotted_name) @import.module
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
WRAPPER_TYPES = {"function_definition", "class_definition"}


def resolve_definition_node(def_node):
    """Unwrap to the decorated_definition parent, if present, so decorators aren't lost."""
    if def_node.parent is not None and def_node.parent.type == "decorated_definition":
        return def_node.parent
    return def_node


def resolve_parent_class(def_node, captures: dict, content: bytes) -> str | None:
    """Return the owning class name for Python methods."""
    from app.ingestion.source_text import node_text

    parent = def_node.parent
    if parent is not None and parent.type == "block":
        grandparent = parent.parent
        if grandparent is not None and grandparent.type == "class_definition":
            name_node = grandparent.child_by_field_name("name")
            if name_node is not None:
                return node_text(name_node, content)
    return None


def get_member_info(node, content: bytes):
    """For class-skeleton building: identify a method node and its stub signature."""
    from app.ingestion.source_text import node_text

    function_node = None
    decorators: list[str] = []

    if node.type == "decorated_definition":
        inner = node.child_by_field_name("definition")
        if inner is not None and inner.type == "function_definition":
            function_node = inner
            decorators = [
                node_text(child, content)
                for child in node.children
                if child.type == "decorator"
            ]
    elif node.type == "function_definition":
        function_node = node

    if function_node is None:
        return None

    name = node_text(function_node.child_by_field_name("name"), content)
    params = node_text(function_node.child_by_field_name("parameters"), content)
    prefix = "async def" if any(child.type == "async" for child in function_node.children) else "def"

    return {"name": name, "params": params, "decorators": decorators, "prefix": prefix}
