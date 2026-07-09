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

(field_definition
   (property_identifier) @func.name
   (arrow_function
     parameters: (formal_parameters) @func.params
   )
 ) @func.def
"""

CLASS_NODE_TYPES = {"class_declaration"}
WRAPPER_TYPES = {"function_declaration"}  # arrow functions/methods aren't re-parseable standalone wrappers the same way


def resolve_definition_node(def_node):
    """JS has no decorator-wrapper node equivalent to Python's — nothing to unwrap."""
    return def_node

def resolve_parent_class(def_node, captures: dict, content: bytes) -> str | None:
    """Handles both method_definition (class methods) and arrow functions assigned
    as class fields. Distinguishes real class methods from object-literal methods
    by requiring the grandparent to be class_declaration/class_expression, not
    object. Verified against a real parse tree — see
    tests/test_resolve_parent_class.py.
    """
    from app.ingestion.chunk_builder_helpers import node_text

    target = def_node
    if target.type == "arrow_function" and target.parent is not None and target.parent.type == "field_definition":
        target = target.parent

    parent = target.parent
    if parent is None or parent.type != "class_body":
        return None

    grandparent = parent.parent
    if grandparent is None or grandparent.type not in ("class_declaration", "class_expression"):
        return None

    name_node = grandparent.child_by_field_name("name")
    if name_node is None:
        return None
    return node_text(name_node, content)


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