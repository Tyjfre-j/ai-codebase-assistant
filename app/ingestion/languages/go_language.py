import tree_sitter_go as _ts_go
from tree_sitter import Language

from app.ingestion.source_text import node_text

QUERY = """
(function_declaration
  name: (identifier) @func.name
  parameters: (parameter_list) @func.params
) @func.def

(method_declaration
  receiver: (parameter_list) @func.receiver
  name: (field_identifier) @func.name
  parameters: (parameter_list) @func.params
) @func.def

(type_declaration
  (type_spec
    name: (type_identifier) @class.name
    type: (struct_type) @class.body
  )
) @class.def

(type_declaration
  (type_spec
    name: (type_identifier) @interface.name
    type: (interface_type) @interface.body
  )
) @interface.def

(import_declaration
  (import_spec
    name: (package_identifier)? @import.alias
    path: (interpreted_string_literal) @import.module
  )
) @import.stmt

(import_declaration
  (import_spec_list
    (import_spec
      name: (package_identifier)? @import.alias
      path: (interpreted_string_literal) @import.module
    )
  )
) @import.stmt
"""
REF_QUERY = """
(call_expression
  function: (identifier) @reference.call
)

(call_expression
  function: (selector_expression
    operand: (_) @reference.call.object
    field: (field_identifier) @reference.call.attr
  )
)

(field_declaration
  type: (type_identifier) @reference.base_class
  !name
)
"""

CLASS_NODE_TYPES: set[str] = set()
FILE_EXTENSION = ".go"

# Go import paths are already slash-separated (e.g. "os/exec"), unlike
# Python's dotted module names, and can legitimately contain literal dots in
# a path segment (e.g. "gopkg.in/yaml.v2") — those must not be turned into
# extra path separators.
PATH_USES_DOTS = False

# A Go import path resolves to a *package directory* containing many .go
# files, never to one file named after the import path.
RESOLVES_IMPORT_TO_DIRECTORY = True


def get_language() -> Language:
    return Language(_ts_go.language())

def unwrap_decorated_definition_node(def_node):
    """Return Go definitions as-is because Go has no decorator wrapper."""
    return def_node  # no decorator-equivalent wrapper in Go


def get_definition_name(node, content: bytes) -> str:
    """Pull the identifier name out of a function/method/type declaration node."""
    name_node = node.child_by_field_name("name")
    if name_node is None and node.type == "type_declaration":
        # class.def/interface.def capture the outer type_declaration, but its
        # name lives on the nested type_spec (struct/interface), not directly
        # on type_declaration itself.
        type_spec = next(
            (child for child in node.children if child.type == "type_spec"), None
        )
        if type_spec is not None:
            name_node = type_spec.child_by_field_name("name")
    if name_node is None:
        return "<anonymous>"
    return node_text(name_node, content)


def get_enclosing_class_name(def_node, captures: dict, content: bytes) -> str | None:
    """Return the receiver type name for Go methods."""
    if def_node.type != "method_declaration":
        return None

    receiver = def_node.child_by_field_name("receiver")
    if receiver is None:
        return None

    parameter_declaration = next(
        (child for child in receiver.children if child.type == "parameter_declaration"),
        None,
    )
    if parameter_declaration is None:
        return None

    for child in parameter_declaration.children:
        if child.type == "type_identifier":
            return node_text(child, content)
        if child.type == "pointer_type":
            inner_type = next(
                (grandchild for grandchild in child.children if grandchild.type == "type_identifier"),
                None,
            )
            if inner_type is not None:
                return node_text(inner_type, content)

    return None


def get_class_member_stub_info(node, content: bytes):
    """Return no class member stubs because Go methods are not tree-nested."""
    return None

def get_module_index_filename() -> str | None:
    return None


def derive_import_bound_name(module_text: str) -> str:
    """Derive the identifier a Go import is referenced by at call sites.

    Go's `import "encoding/json"` has no explicit bound-name node in the
    grammar for the unaliased case — the identifier used in code (`json.Marshal`)
    is implicit: the last segment of the import path. An explicit local name
    (`import j "encoding/json"`) is still captured separately as `import.alias`
    and takes precedence over this.
    """
    text = module_text.strip("\"'`")
    return text.rstrip("/").rsplit("/", 1)[-1]

BUILTINS = {
    "append", "cap", "clear", "close", "complex", "copy", "delete", "imag",
    "len", "make", "new", "panic", "print", "println", "real", "recover",
    "int", "int8", "int16", "int32", "int64", "uint", "uint8", "uint16",
    "uint32", "uint64", "uintptr", "float32", "float64", "complex64",
    "complex128", "string", "bool", "byte", "rune", "error"
}

def is_builtin(name: str) -> bool:
    return name in BUILTINS