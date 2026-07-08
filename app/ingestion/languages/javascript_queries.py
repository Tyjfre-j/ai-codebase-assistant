JS_QUERY = """
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
  name: (identifier) @class.name
) @class.def

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
"""

CLASS_NODE_TYPES = {"class_declaration"}
WRAPPER_TYPES = {"function_declaration"}  # arrow functions/methods aren't re-parseable standalone wrappers the same way


def resolve_definition_node(def_node):
    """JS has no decorator-wrapper node equivalent to Python's — nothing to unwrap."""
    return def_node


def get_member_info(node, content: bytes):
    """Best-effort: JS decorators are a newer/unstable grammar feature — verify on the
    playground for your actual grammar version before trusting the decorator extraction here."""
    from app.ingestion.chunk_builder_helpers import node_text

    if node.type != "method_definition":
        return None

    name = node_text(node.child_by_field_name("name"), content)
    params = node_text(node.child_by_field_name("parameters"), content)
    is_async = any(c.type == "async" for c in node.children)
    decorators = [node_text(c, content) for c in node.children if c.type == "decorator"]
    return {
        "name": name,
        "params": params,
        "decorators": decorators,
        "prefix": "async" if is_async else "",
    }