from tree_sitter import Node, Query, QueryCursor

from app.ingestion.code_chunk import CodeChunk, RefRecord
from app.ingestion.source_parser import ParsedFile
from app.ingestion.source_text import node_text


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


def extract_reference_records(node: Node, content: bytes, ref_query: Query) -> list[RefRecord]:
    """Extract raw (unresolved) call/inheritance references from one chunk's node."""
    cursor = QueryCursor(ref_query)
    raw_captures = cursor.captures(node)

    captures_by_name: dict[str, list[Node]] = {}
    if isinstance(raw_captures, dict):
        for capture_name, nodes in raw_captures.items():
            captures_by_name.setdefault(capture_name, []).extend(nodes)
    else:
        for captured_node, capture_name in raw_captures:
            captures_by_name.setdefault(capture_name, []).append(captured_node)

    references: list[RefRecord] = []

    for call_node in captures_by_name.get("reference.call", []):
        references.append(RefRecord(
            text=node_text(call_node, content),
            kind="call",
            points_to=None,
        ))

    attribute_pairs: dict[tuple[int, int], dict[str, Node]] = {}
    for object_node in captures_by_name.get("reference.call.object", []):
        parent = object_node.parent
        key = (parent.start_byte, parent.end_byte)
        attribute_pairs.setdefault(key, {})["object"] = object_node
    for attr_node in captures_by_name.get("reference.call.attr", []):
        parent = attr_node.parent
        key = (parent.start_byte, parent.end_byte)
        attribute_pairs.setdefault(key, {})["attr"] = attr_node

    for pair in attribute_pairs.values():
        if "object" in pair and "attr" in pair:
            text = f"{node_text(pair['object'], content)}.{node_text(pair['attr'], content)}"
            references.append(RefRecord(
                text=text,
                kind="call",
                points_to=None,
            ))

    for base_class_node in captures_by_name.get("reference.base_class", []):
        references.append(RefRecord(
            text=node_text(base_class_node, content),
            kind="inheritance",
            points_to=None,
        ))

    return references


def populate_chunk_references_for_file(parsed: ParsedFile, chunks: list[CodeChunk]) -> None:
    """Populate `references` on every chunk from this file, mutating in place."""
    for chunk in chunks:
        if chunk.kind in ("leftover", "merged_group", "class_skeleton"):
            continue
        node = find_node_for_range(parsed.tree.root_node, chunk.start_byte, chunk.end_byte)
        chunk.references = extract_reference_records(node, parsed.content, parsed.ref_query)