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
REF_QUERY = ""

CLASS_NODE_TYPES: set[str] = set()
STRUCT_NODE_TYPES = {"type_declaration"}     # only when type_spec.type == struct_type
INTERFACE_NODE_TYPES = {"type_declaration"}  # only when type_spec.type == interface_type
WRAPPER_TYPES = {"function_declaration", "method_declaration"}


def unwrap_decorated_definition_node(def_node):
    """Return Go definitions as-is because Go has no decorator wrapper."""
    return def_node  # no decorator-equivalent wrapper in Go


def get_enclosing_class_name(def_node, captures: dict, content: bytes) -> str | None:
    """Return the receiver type name for Go methods."""
    from app.ingestion.source_text import node_text

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
