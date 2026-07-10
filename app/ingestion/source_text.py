import hashlib

from tree_sitter import Node

from app.core.exceptions import ChunkDecodeError


def node_text(node: Node, content: bytes) -> str:
    try:
        return content[node.start_byte:node.end_byte].decode("utf-8")
    except UnicodeDecodeError as e:
        raise ChunkDecodeError(
            f"Failed to decode bytes {node.start_byte}-{node.end_byte} "
            f"(node type={node.type}): {e}"
        ) from e


def node_text_range(start: int, end: int, content: bytes) -> str:
    try:
        return content[start:end].decode("utf-8")
    except UnicodeDecodeError as e:
        raise ChunkDecodeError(f"Failed to decode bytes {start}-{end}: {e}") from e

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

def stable_chunk_id(file_path: str, start_byte: int, qualified_name: str) -> str:
    """Deterministic id: stable across re-runs unless the chunk moves or is renamed.
    Unlike a random uuid4, re-chunking an unchanged file produces the same ids,
    which is what lets incremental re-indexing skip unchanged chunks later.
    """
    raw = f"{file_path}:{start_byte}:{qualified_name}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
