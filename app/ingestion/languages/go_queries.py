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

STRUCT_NODE_TYPES = {"type_declaration"}     # only when type_spec.type == struct_type
INTERFACE_NODE_TYPES = {"type_declaration"}  # only when type_spec.type == interface_type
WRAPPER_TYPES = {"function_declaration", "method_declaration"}


def resolve_definition_node(def_node):
    return def_node  # no decorator-equivalent wrapper in Go


def resolve_parent_class(def_node, captures: dict, content: bytes) -> str | None:
    """Go has no nested-class concept; the equivalent is a method's receiver type,
    e.g. `func (f *Foo) Bar()` or `func (f Foo) Bar()`. Both pointer and value
    receivers are handled. Verified against a real parse tree — see
    tests/test_resolve_parent_class.py.
    """
    from app.ingestion.chunk_builder_helpers import node_text

    if def_node.type != "method_declaration":
        return None

    receiver = def_node.child_by_field_name("receiver")
    if receiver is None:
        return None

    param_decl = next((c for c in receiver.children if c.type == "parameter_declaration"), None)
    if param_decl is None:
        return None

    for c in param_decl.children:
        if c.type == "type_identifier":
            return node_text(c, content)
        if c.type == "pointer_type":
            inner = next((gc for gc in c.children if gc.type == "type_identifier"), None)
            if inner is not None:
                return node_text(inner, content)

    return None

def get_member_info(node, content: bytes):
    """Go struct bodies contain only fields, never methods — always kept verbatim.
    Interface bodies contain method_elem signatures with no bodies at all; not yet
    handled here — decide if the skeleton view should list these separately."""
    return None