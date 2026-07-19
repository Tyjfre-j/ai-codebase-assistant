from tree_sitter import Node, Query, QueryCursor

from app.ingestion.code_chunk import RefKind, RefRecord
from app.ingestion.source_text import node_text


def _find_owner(call_node: Node, chunk_root: Node, definition_ids: set[int] | None, content: bytes) -> str | None:
    """Walk up from a call/attribute node to find which direct member of chunk_root contains it."""
    if definition_ids is None:
        return None
    current = call_node.parent
    while current is not None and current.id != chunk_root.id:
        if current.id in definition_ids:
            name_node = current.child_by_field_name("name") or current.child_by_field_name("property")
            return node_text(name_node, content) if name_node is not None else None
        current = current.parent
    return None


def extract_reference_records(
    node: Node,
    content: bytes,
    ref_query: Query,
    definition_ids: set[int] | None = None,
) -> list[RefRecord]:
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
            kind=RefKind.CALL,
            points_to=None,
            owner_name=_find_owner(call_node, node, definition_ids, content),
        ))

    attribute_pairs: dict[tuple[int, int], dict[str, Node]] = {}
    for object_node in captures_by_name.get("reference.call.object", []):
        parent = object_node.parent
        if parent is None:
            continue
        key = (parent.start_byte, parent.end_byte)
        attribute_pairs.setdefault(key, {})["object"] = object_node
    for attr_node in captures_by_name.get("reference.call.attr", []):
        parent = attr_node.parent
        if parent is None:
            continue
        key = (parent.start_byte, parent.end_byte)
        attribute_pairs.setdefault(key, {})["attr"] = attr_node

    for pair in attribute_pairs.values():
        if "object" in pair and "attr" in pair:
            text = f"{node_text(pair['object'], content)}.{node_text(pair['attr'], content)}"
            references.append(RefRecord(
                text=text,
                kind=RefKind.CALL,
                points_to=None,
                owner_name=_find_owner(pair["object"], node, definition_ids, content),
            ))

    for base_class_node in captures_by_name.get("reference.base_class", []):
        references.append(RefRecord(
            text=node_text(base_class_node, content),
            kind=RefKind.INHERITANCE,
            points_to=None,
        ))

    return references