from tree_sitter import Node

from app.ingestion.code_chunk import ChunkKind
from app.ingestion.languages import (
    CLASS_DEF_CAPTURE,
    FUNC_DEF_CAPTURE,
    INTERFACE_DEF_CAPTURE,
)


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


def _classify_definition(
    node: Node,
    definition_ids: set[int],
    definition_kind_by_id: dict[int, str],
    budget: int,
    memo: dict[int, bool],
    enclosing_def_node: Node | None,
    file_path: str,
) -> list[tuple[str, list[Node], Node | None]]:
    """Classify a captured definition node: whole, skeleton+recurse, or oversized-whole."""
    size = node.end_byte - node.start_byte
    kind = definition_kind_by_id[node.id]

    # Fits budget → whole definition
    if size <= budget:
        return [(ChunkKind.DEFINITION, [node], enclosing_def_node)]

    has_nested = any(_contains_definition(c, definition_ids, memo) for c in node.children)

    # Class with nested defs → skeleton + recurse
    if kind == CLASS_DEF_CAPTURE and has_nested:
        return [(ChunkKind.CLASS_SKELETON, [node], enclosing_def_node)] + _walk_children(
            node, definition_ids, definition_kind_by_id, budget, memo, node, file_path
        )

    # Interface with nested defs → skeleton + recurse
    if kind == INTERFACE_DEF_CAPTURE and has_nested:
        return [(ChunkKind.CLASS_SKELETON, [node], enclosing_def_node)] + _walk_children(
            node, definition_ids, definition_kind_by_id, budget, memo, node, file_path
        )

    # Function with nested defs → skeleton + recurse
    if kind == FUNC_DEF_CAPTURE and has_nested:
        return [(ChunkKind.FUNCTION_SKELETON, [node], enclosing_def_node)] + _walk_children(
            node, definition_ids, definition_kind_by_id, budget, memo, node, file_path
        )

    # Oversized leaf — keep whole anyway (nothing to extract)
    return [(ChunkKind.DEFINITION, [node], enclosing_def_node)]


def _walk(
    node: Node,
    definition_ids: set[int],
    definition_kind_by_id: dict[int, str],
    budget: int,
    memo: dict[int, bool],
    enclosing_def_node: Node | None,
    file_path: str,
) -> list[tuple[str, list[Node], Node | None]]:
    """Classify a subtree as definition or children."""
    if node.id in definition_ids:
        return _classify_definition(
            node, definition_ids, definition_kind_by_id, budget, memo, enclosing_def_node, file_path
        )

    return _walk_children(node, definition_ids, definition_kind_by_id, budget, memo, enclosing_def_node, file_path)


def _walk_children(
    node: Node,
    definition_ids: set[int],
    definition_kind_by_id: dict[int, str],
    budget: int,
    memo: dict[int, bool],
    enclosing_def_node: Node | None,
    file_path: str,
) -> list[tuple[str, list[Node], Node | None]]:
    """Walk children into ordered chunk candidates."""
    emitted: list[tuple[str, list[Node], Node | None]] = []

    for child in node.children:
        emitted.extend(
            _walk(child, definition_ids, definition_kind_by_id, budget, memo, enclosing_def_node, file_path)
        )

    return emitted


def walk_top_level(
    root: Node,
    definition_ids: set[int],
    definition_kind_by_id: dict[int, str],
    budget: int,
    file_path: str,
) -> list[tuple[str, list[Node], Node | None]]:
    """Walk the root's children into ordered chunk candidates."""
    memo: dict[int, bool] = {}
    return _walk_children(root, definition_ids, definition_kind_by_id, budget, memo, None, file_path)