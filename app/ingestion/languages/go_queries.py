GO_QUERY = """
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

CLASS_NODE_TYPES = {"type_declaration"}  # unused by Go's own resolver, kept for interface consistency
WRAPPER_TYPES = {"function_declaration", "method_declaration"}


def resolve_definition_node(def_node):
    return def_node  # no decorator-equivalent wrapper in Go


def resolve_parent_class(captures: dict, content: bytes) -> str | None:
    """Go-specific: pull the receiver's type name out of the parameter_list node
    captured as func.receiver — e.g. "(u *User)" or "(u User)" -> "User".

    NOT VERIFIED on the playground — the receiver's inner shape (parameter_declaration
    with a pointer_type wrapping a type_identifier) is my best recollection of Go's
    grammar, not something we've tested like everything else in this file. Check this
    on a real Go method before trusting it.
    """
    from app.ingestion.chunk_builder_helpers import node_text

    if "func.receiver" not in captures:
        return None
    receiver_node = captures["func.receiver"][0]
    for child in receiver_node.named_children:
        if child.type != "parameter_declaration":
            continue
        type_node = child.child_by_field_name("type")
        if type_node is None:
            continue
        if type_node.type == "pointer_type":
            type_node = type_node.named_children[0] if type_node.named_children else type_node
        return node_text(type_node, content)
    return None


def get_member_info(node, content: bytes):
    """Go struct bodies contain only fields, never methods — always kept verbatim."""
    return None