import tree_sitter_typescript as _ts_typescript
from tree_sitter import Language

from app.ingestion.source_text import node_text

QUERY = """
(function_declaration
  name: (identifier) @func.name
  parameters: (formal_parameters) @func.params
) @func.def

(method_definition
  name: (property_identifier) @func.name
  parameters: (formal_parameters) @func.params
) @func.def

(variable_declarator
  name: (identifier) @func.name
  value: (arrow_function
    parameters: (formal_parameters) @func.params
  )
) @func.def

(class_declaration
  name: (type_identifier) @class.name
) @class.def

(interface_declaration
  name: (type_identifier) @interface.name
) @interface.def

(import_statement
  (import_clause
    (named_imports
      (import_specifier
        name: (identifier) @import.bound_name
        alias: (identifier)? @import.alias
      )
    )
  )
  source: (string) @import.module
) @import.stmt

(import_statement
  (import_clause
    (identifier) @import.bound_name
  )
  source: (string) @import.module
) @import.stmt

(import_statement
  (import_clause
    (namespace_import
      (identifier) @import.bound_name
    )
  )
  source: (string) @import.module
) @import.stmt

(import_statement
  "import" . source: (string) @import.module
) @import.stmt

(public_field_definition
   (property_identifier) @func.name
   (arrow_function
     parameters: (formal_parameters) @func.params
   )
 ) @func.def
"""
REF_QUERY = """
(call_expression
  function: (identifier) @reference.call
)

(call_expression
  function: (member_expression
    object: (_) @reference.call.object
    property: (property_identifier) @reference.call.attr
  )
)

(extends_clause
  value: (identifier) @reference.base_class
)
"""

CLASS_NODE_TYPES = {"class_declaration"}
_FIELD_DEFINITION_TYPE = "public_field_definition"
FILE_EXTENSION = ".ts"


def get_language() -> Language:
    return Language(_ts_typescript.language_typescript())

def unwrap_decorated_definition_node(def_node):
    """Return TypeScript definitions as-is because no wrapper is normalized here."""
    return def_node

def _unwrap_arrow_field(definition_node):
    """If this arrow function is the value of a public class field, return the
    enclosing public_field_definition node — that's what's parented under class_body."""
    if (
        definition_node.type == "arrow_function"
        and definition_node.parent is not None
        and definition_node.parent.type == _FIELD_DEFINITION_TYPE
    ):
        return definition_node.parent
    return definition_node

def get_definition_name(node, content: bytes) -> str:
    """Pull the identifier name out of a function/method/arrow-field definition node."""
    name_node = node.child_by_field_name("name") or node.child_by_field_name("property")
    if name_node is None:
        return "<anonymous>"
    return node_text(name_node, content)

def get_enclosing_class_name(def_node, captures: dict, content: bytes) -> str | None:
    """Return the owning class for TS methods and public-field arrow functions."""
    definition_node = _unwrap_arrow_field(def_node)

    parent = definition_node.parent
    if parent is None or parent.type != "class_body":
        return None

    grandparent = parent.parent
    if grandparent is None or grandparent.type not in ("class_declaration", "class_expression"):
        return None

    name_node = grandparent.child_by_field_name("name")
    if name_node is None:
        return None
    return node_text(name_node, content)

def get_namespace(def_node, captures: dict, content: bytes) -> list[str]:
    """Walk up the AST and return the full namespace path."""
    namespace = []
    current = def_node.parent
    while current is not None:
        if current.type in (
            "class_declaration", "class_expression", "function_declaration",
            "method_definition", "variable_declarator", _FIELD_DEFINITION_TYPE
        ):
            name_node = current.child_by_field_name("name") or current.child_by_field_name("property")
            if name_node is not None:
                namespace.append(node_text(name_node, content))
        current = current.parent
    return list(reversed(namespace))

def get_class_member_stub_info(node, content: bytes):
    """Return a class-member signature for TypeScript class skeleton chunks.

    Handles both `method_definition` members and class-field arrow functions
    (`public_field_definition` whose value is an arrow_function). The latter
    are already chunked individually as their own DEFINITIONs via the QUERY's
    public_field_definition pattern, but were previously always excluded from
    the class's own skeleton listing, silently under-representing its member set.
    """
    if node.type == "method_definition":
        name = node_text(node.child_by_field_name("name"), content)
        params = node_text(node.child_by_field_name("parameters"), content)
        is_async = any(child.type == "async" for child in node.children)
        decorators = [
            node_text(child, content)
            for child in node.children
            if child.type == "decorator"
        ]
        return {
            "name": name,
            "params": params,
            "decorators": decorators,
            "prefix": "async" if is_async else "",
        }

    if node.type == _FIELD_DEFINITION_TYPE:
        value = node.child_by_field_name("value")
        if value is None or value.type != "arrow_function":
            return None
        name = node_text(node.child_by_field_name("name"), content)
        params = node_text(value.child_by_field_name("parameters"), content)
        is_async = any(child.type == "async" for child in value.children)
        return {
            "name": name,
            "params": params,
            "decorators": [],
            "prefix": "async" if is_async else "",
        }

    return None

def get_class_skeleton_header(name: str) -> str:
    return f"class {name} {{"

def get_class_skeleton_footer() -> str | None:
    return "}"

def get_module_index_filename() -> str | None:
    return "index.ts"

BUILTINS = {
    "console", "Math", "JSON", "Object", "Array", "String", "Number", "Boolean",
    "Date", "RegExp", "Error", "Promise", "Map", "Set", "WeakMap", "WeakSet",
    "Symbol", "Proxy", "Reflect", "parseInt", "parseFloat", "isNaN", "isFinite",
    "decodeURI", "decodeURIComponent", "encodeURI", "encodeURIComponent",
    "setTimeout", "clearTimeout", "setInterval", "clearInterval", "window",
    "document", "fetch", "process", "require", "module", "exports"
}

def is_builtin(name: str) -> bool:
    return name in BUILTINS