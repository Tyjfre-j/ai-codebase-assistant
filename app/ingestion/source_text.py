import hashlib

from tree_sitter import Node

from app.core.constants import CHUNK_ID_HEX_LENGTH
from app.core.exceptions import ChunkDecodeError


def node_text_range(start: int, end: int, content: bytes) -> str:
    """Return the UTF-8 string for a byte range in the source content."""
    try:
        return content[start:end].decode("utf-8")
    except UnicodeDecodeError as e:
        raise ChunkDecodeError(f"Failed to decode bytes {start}-{end}: {e}") from e

def node_text(node: Node, content: bytes) -> str:
    """Return the UTF-8 string for a node's byte range in the source content."""
    try:
        return node_text_range(node.start_byte, node.end_byte, content)
    except ChunkDecodeError as e:
        raise ChunkDecodeError(f"{e} (node type={node.type})") from e

def stable_chunk_id(file_path: str, start_byte: int, full_name: str) -> str:
    """Deterministic id: stable across re-runs unless the chunk moves or is renamed."""
    raw = f"{file_path}:{start_byte}:{full_name}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:CHUNK_ID_HEX_LENGTH]