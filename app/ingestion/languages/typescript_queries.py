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

CLASS_NODE_TYPES = {"class_declaration"}
INTERFACE_NODE_TYPES = {"interface_declaration"}
WRAPPER_TYPES = {"function_declaration"}


def resolve_definition_node(def_node):
    return def_node


def resolve_parent_class(def_node, captures: dict, content: bytes) -> str | None:
    """Same structure as JavaScript, but TS uses public_field_definition (not
    field_definition) for a class field with an initializer. Interfaces have no
    'parent class' concept — method_signature's parent is interface_body, not
    class_body, so this naturally returns None for interface members. Verified
    against a real parse tree — see tests/test_resolve_parent_class.py.
    """
    from app.ingestion.chunk_builder_helpers import node_text

    target = def_node
    if target.type == "arrow_function" and target.parent is not None and target.parent.type == "public_field_definition":
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