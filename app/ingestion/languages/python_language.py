import tree_sitter_python as _ts_python
from tree_sitter import Language, Node

from app.ingestion.source_text import node_text, node_text_range

QUERY = """
(function_definition
  name: (identifier) @func.name
  parameters: (parameters) @func.params
) @func.def

(class_definition
  name: (identifier) @class.name
) @class.def

(import_statement
  name: (dotted_name
    . (identifier) @import.bound_name
  ) @import.module
) @import.stmt

(import_statement
  name: (aliased_import
    name: (dotted_name) @import.module
    alias: (identifier) @import.bound_name
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

(class_definition
  superclasses: (argument_list
    (attribute) @reference.base_class
  )
)
"""

DECORATED_DEFINITION_NODE_TYPES = {"decorated_definition"}
FUNCTION_DEFINITION_NODE_TYPES = {"function_definition"}
CLASS_DEFINITION_NODE_TYPES = {"class_definition"}
INTERFACE_DEFINITION_NODE_TYPES: set[str] = set()
DEFINITION_NODE_TYPES = (
    FUNCTION_DEFINITION_NODE_TYPES
    | CLASS_DEFINITION_NODE_TYPES
    | INTERFACE_DEFINITION_NODE_TYPES
)

FILE_EXTENSION = ".py"


def get_language() -> Language:
    return Language(_ts_python.language())


def get_decoration_of_definition_node(def_node):
    """Check if the node has a decoration wapper, if yes return it otherwise return the node itself."""
    if def_node.parent is not None and def_node.parent.type in DECORATED_DEFINITION_NODE_TYPES:
        return def_node.parent
    return def_node

def get_node_name(node: Node) -> Node | None:
    return get_actual_definition_node(node).child_by_field_name("name")

def get_node_body(node: Node) -> Node | None:
    return get_actual_definition_node(node).child_by_field_name("body")

def get_actual_definition_node(node):
    """Return the actual definition node, unwrapping decorators if needed."""
    if node.type in DECORATED_DEFINITION_NODE_TYPES:
        inner = node.child_by_field_name("definition")
        return inner if inner is not None else node
    return node

def get_actual_definition_type(node) -> str:
    """Return the real definition type string, unwrapping decorators if needed."""
    return get_actual_definition_node(node).type

def get_definition_name(node, content: bytes) -> str:
    """Pull the identifier name out of a (possibly decorator-wrapped) definition"""
    target = get_actual_definition_node(node)
    name_node = target.child_by_field_name("name")
    if name_node is None:
        return "<anonymous>"
    return node_text(name_node, content)

def get_enclosing_class_name(def_node, content: bytes) -> str | None:
    """Walk up the AST to find the nearest enclosing class name."""
    current = def_node.parent
    while current is not None:
        if current.type in CLASS_DEFINITION_NODE_TYPES:
            name_node = current.child_by_field_name("name")
            if name_node is not None:
                return node_text(name_node, content)
        current = current.parent
    return None

def get_ancestor_namespace(def_node, captures: dict, content: bytes) -> list[str]:
    """Walk up the AST and return all ancestor definition names (classes and functions).
    Returns reversed list: ['OuterClass', 'outer_func'] for OuterClass.outer_func.inner."""
    namespace = []
    current = def_node.parent
    while current is not None:
        if current.type in CLASS_DEFINITION_NODE_TYPES or current.type in FUNCTION_DEFINITION_NODE_TYPES:
            name_node = current.child_by_field_name("name")
            if name_node is not None:
                namespace.append(node_text(name_node, content))
        current = current.parent
    return list(reversed(namespace))

def get_signature_text(node, content: bytes) -> str | None:
    """Raw source text from node's true start (decorators included) up to
    where its body begins. Works for functions, classes, interfaces, any
    nesting depth. Returns None if node isn't a definition at all."""
    actual = get_actual_definition_node(node)
    if actual.type not in DEFINITION_NODE_TYPES:
        return None
    body = get_node_body(actual)
    if body is None:
        return node_text(node, content).rstrip()
    return node_text_range(node.start_byte, body.start_byte, content).rstrip()

def get_class_footer() -> str | None:
    """Return the closing line for a class skeleton, or None if not needed."""
    return None

def get_package_index_filename() -> str | None:
    """Return the filename that marks a package directory, or None."""
    return "__init__.py"

# Python's package system makes "from X import Y" genuinely ambiguous between
# "Y is a symbol in X's own __init__.py" and "Y is X's submodule, its own
# file/subpackage" — both are idiomatic and common (the latter especially with
# generated code, e.g. sqlc). JS/TS's ES modules and Go's package imports have
# no equivalent ambiguity: a named import always refers to something exported
# by the exact file/path given, never to a differently-named nested file.
ALLOWS_SUBMODULE_IMPORTS = True

BUILTINS = {
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes", "callable", "chr",
    "classmethod", "compile", "complex", "delattr", "dict", "dir", "divmod", "enumerate",
    "eval", "exec", "filter", "float", "format", "frozenset", "getattr", "globals",
    "hasattr", "hash", "help", "hex", "id", "input", "int", "isinstance", "issubclass",
    "iter", "len", "list", "locals", "map", "max", "memoryview", "min", "next", "object",
    "oct", "open", "ord", "pow", "print", "property", "range", "repr", "reversed", "round",
    "set", "setattr", "slice", "sorted", "staticmethod", "str", "sum", "super", "tuple",
    "type", "vars", "zip", "__import__", "Exception", "ValueError", "TypeError",
    "RuntimeError", "KeyError", "IndexError", "AttributeError", "ImportError"
}

def is_builtin(name: str) -> bool:
    return name in BUILTINS