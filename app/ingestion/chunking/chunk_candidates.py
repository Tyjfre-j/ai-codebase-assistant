from tree_sitter import Node

from app.ingestion.code_chunk import ChunkKind
from app.ingestion.source_text import stable_chunk_id


def _contains_definition(node: Node, definition_ids: set[int], memo: dict[int, bool]) -> bool:
    """Return whether this node or any descendant is a captured definition."""
    cached = memo.get(node.id)
    if cached is not None:
        return cached
    if node.id in definition_ids:
        result = True
    else:
        result = any(_contains_definition(c, definition_ids, memo) for c in node.children)
    memo[node.id] = result
    return result


def _scope_id_for(node: Node, file_path: str) -> str:
    """Return a stable identifier for a scope-introducing node."""
    return stable_chunk_id(file_path, node.start_byte, f"<scope:{node.start_byte}>")


def _classify_definition(
    node: Node,
    definition_ids: set[int],
    budget: int,
    class_node_types: set[str],
    memo: dict[int, bool],
    enclosing_def_node: Node | None,
    file_path: str,
) -> list[tuple[str, list[Node], Node | None, str | None]]:
    """Classify a captured definition node: whole, skeleton+recurse, or oversized-whole."""
    size = node.end_byte - node.start_byte

    # Class: fits budget → whole definition, else skeleton + recurse with absorption
    if node.type in class_node_types:
        if size <= budget:
            return [(ChunkKind.DEFINITION, [node], enclosing_def_node, None)]
        return [(ChunkKind.CLASS_SKELETON, [node], enclosing_def_node, None)] + _walk_children(
            node, definition_ids, budget, class_node_types, memo, node, file_path,
            absorb_leftovers=True
        )

    # Function/method: fits budget → whole
    if size <= budget:
        return [(ChunkKind.DEFINITION, [node], enclosing_def_node, None)]

    # Oversized function with nested defs → skeleton + recurse with absorption
    has_nested = any(_contains_definition(c, definition_ids, memo) for c in node.children)
    if has_nested:
        return [(ChunkKind.FUNCTION_SKELETON, [node], enclosing_def_node, None)] + _walk_children(
            node, definition_ids, budget, class_node_types, memo, node, file_path,
            absorb_leftovers=True
        )

    # Oversized leaf — keep whole anyway
    return [(ChunkKind.DEFINITION, [node], enclosing_def_node, None)]


def _walk(
    node: Node,
    definition_ids: set[int],
    budget: int,
    class_node_types: set[str],
    memo: dict[int, bool],
    enclosing_def_node: Node | None,
    file_path: str,
) -> list[tuple[str, list[Node], Node | None, str | None]]:
    """Classify a subtree as definition, skeleton, leftover, or children."""
    if node.id in definition_ids:
        return _classify_definition(
            node, definition_ids, budget, class_node_types, memo, enclosing_def_node, file_path
        )

    if not _contains_definition(node, definition_ids, memo):
        return [(ChunkKind.LEFTOVER, [node], enclosing_def_node, None)]

    return _walk_children(node, definition_ids, budget, class_node_types, memo, enclosing_def_node, file_path)


def _walk_children(
    node: Node,
    definition_ids: set[int],
    budget: int,
    class_node_types: set[str],
    memo: dict[int, bool],
    enclosing_def_node: Node | None,
    file_path: str,
    absorb_leftovers: bool = False,
) -> list[tuple[str, list[Node], Node | None, str | None]]:
    """Walk children, keeping adjacent leftover nodes grouped together."""
    emitted: list[tuple[str, list[Node], Node | None, str | None]] = []
    leftover_buffer: list[Node] = []

    for child in node.children:
        for kind, nodes, parent, scope in _walk(
            child, definition_ids, budget, class_node_types, memo, enclosing_def_node, file_path
        ):
            if kind == ChunkKind.LEFTOVER:
                if absorb_leftovers:
                    continue
                leftover_buffer.extend(nodes)
            else:
                if leftover_buffer:
                    emitted.append((ChunkKind.LEFTOVER, leftover_buffer, enclosing_def_node, None))
                    leftover_buffer = []
                emitted.append((kind, nodes, parent, scope))

    if leftover_buffer and not absorb_leftovers:
        emitted.append((ChunkKind.LEFTOVER, leftover_buffer, enclosing_def_node, None))
    return emitted


def walk_top_level(
    root: Node,
    definition_ids: set[int],
    budget: int,
    class_node_types: set[str],
    file_path: str,
) -> list[tuple[str, list[Node], Node | None, str | None]]:
    """Walk the root's children into ordered chunk candidates."""
    memo: dict[int, bool] = {}
    return _walk_children(root, definition_ids, budget, class_node_types, memo, None, file_path)