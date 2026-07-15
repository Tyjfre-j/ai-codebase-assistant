from torch import chunk
from tree_sitter import Node, Query, QueryCursor

from app.ingestion.code_chunk import CodeChunk, RefRecord
from app.ingestion.source_parser import ParsedFile
from app.ingestion.source_text import node_text

_SKIPPED_CHUNK_KINDS = {"class_skeleton", "leftover", "merged_group"}

def find_node_for_range(root: Node, start_byte: int, end_byte: int) -> Node:
    """Find the smallest AST node in `root`'s tree that fully contains [start_byte, end_byte)."""
    node = root
    while True:
        child_containing_range = None
        for child in node.children:
            if child.start_byte <= start_byte and child.end_byte >= end_byte:
                child_containing_range = child
                break
        if child_containing_range is None:
            return node
        node = child_containing_range

def extract_raw_refs(node: Node, content: bytes, ref_query: Query) -> list[RefRecord]:
    """Extract raw (unresolved) call/inheritance references from one definition chunk's node."""
    cursor = QueryCursor(ref_query)
    raw_captures = cursor.captures(node)

    captures_by_name: dict[str, list[Node]] = {}
    if isinstance(raw_captures, dict):
        for capture_name, nodes in raw_captures.items():
            captures_by_name.setdefault(capture_name, []).extend(nodes)
    else:
        for captured_node, capture_name in raw_captures:
            captures_by_name.setdefault(capture_name, []).append(captured_node)

    refs: list[RefRecord] = []

    for call_node in captures_by_name.get("reference.call", []):
        refs.append(RefRecord(
            raw_name=node_text(call_node, content),
            target_chunk_id=None,
            edge_type="call",
        ))

    objects = captures_by_name.get("reference.call.object", [])
    attrs = captures_by_name.get("reference.call.attr", [])
    for object_node, attr_node in zip(objects, attrs):
        raw_name = f"{node_text(object_node, content)}.{node_text(attr_node, content)}"
        refs.append(RefRecord(
            raw_name=raw_name,
            target_chunk_id=None,
            edge_type="call",
        ))

    for base_class_node in captures_by_name.get("reference.base_class", []):
        refs.append(RefRecord(
            raw_name=node_text(base_class_node, content),
            target_chunk_id=None,
            edge_type="inheritance",
        ))

    return refs

def extract_refs_for_file(parsed: ParsedFile, chunks: list[CodeChunk]) -> list[CodeChunk]:
    """Populate `refs` on every definition-kind chunk from this file, mutating in place."""
    for chunk in chunks:
        if chunk.chunk_kind in _SKIPPED_CHUNK_KINDS:
            continue
        node = find_node_for_range(parsed.tree.root_node, chunk.start_byte, chunk.end_byte)
        chunk.refs = extract_raw_refs(node, parsed.content, parsed.ref_query)

    return chunks