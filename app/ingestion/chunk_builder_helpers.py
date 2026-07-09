from tree_sitter import Node


def node_text(node: Node, content: bytes) -> str:
    """Extract the exact source slice a node spans, decoded to str."""
    return content[node.start_byte:node.end_byte].decode("utf-8")


def node_text_range(start: int, end: int, content: bytes) -> str:
    """Same as node_text, but for a raw byte span with no single Node (e.g. leftover groups)."""
    return content[start:end].decode("utf-8")


def extract_symbol_name(node: Node, content: bytes) -> str:
    """Pull the identifier name out of a (possibly decorator-wrapped) definition node."""
    target = node
    if node.type == "decorated_definition":
        target = node.child_by_field_name("definition") or node

    name_node = target.child_by_field_name("name")
    if name_node is None:
        # field_definition (class field arrow functions, e.g. `bar = () => {}`)
        # uses `property` instead of `name` for the identifier.
        name_node = target.child_by_field_name("property")

    if name_node is None:
        return "<anonymous>"
    return node_text(name_node, content)