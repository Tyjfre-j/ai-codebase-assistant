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
REF_QUERY = ""

CLASS_NODE_TYPES = {"class_declaration"}
INTERFACE_NODE_TYPES = {"interface_declaration"}
WRAPPER_TYPES = {"function_declaration"}


def resolve_definition_node(def_node):
    """Return TypeScript definitions as-is because no wrapper is normalized here."""
    return def_node


def resolve_parent_class(def_node, captures: dict, content: bytes) -> str | None:
    """Return the owning class for TS methods and public-field arrow functions."""
    from app.ingestion.source_text import node_text

    definition_node = def_node
    if (
        definition_node.type == "arrow_function"
        and definition_node.parent is not None
        and definition_node.parent.type == "public_field_definition"
    ):
        definition_node = definition_node.parent

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


def get_member_info(node, content: bytes):
    """Return a class-method signature for TypeScript class skeleton chunks."""
    from app.ingestion.source_text import node_text

    if node.type != "method_definition":
        return None
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
