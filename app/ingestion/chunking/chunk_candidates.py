from tree_sitter import Node

from app.ingestion.code_chunk import ChunkKind


def _contains_definition(node: Node, definition_ids: set[int], memo: dict[int, bool]) -> bool:
    """Return whether this node or any descendant is a captured definition.

    Memoized by `node.id` for the lifetime of a single classification pass
    (one `walk_top_level` call). Without this, the same subtree can be
    re-walked once per ancestor as `_walk` descends through nested
    oversized/ambiguous nodes, which is quadratic in pathological cases.
    """
    cached = memo.get(node.id)
    if cached is not None:
        return cached

    if node.id in definition_ids:
        result = True
    else:
        result = any(
            _contains_definition(child, definition_ids, memo) for child in node.children
        )

    memo[node.id] = result
    return result


def _walk(
    node: Node,
    definition_ids: set[int],
    budget: int,
    class_node_types: set[str],
    memo: dict[int, bool],
) -> list[tuple[str, list[Node]]]:
    """Classify a subtree as a definition, skeleton, leftover, or children."""
    # If this node is a captured definition, it can be a real definition chunk,
    if node.id in definition_ids:
        # if it's a class make a class skeleton chunk and go thru it's children
        if node.type in class_node_types:
            return [(ChunkKind.CLASS_SKELETON, [node])] + _walk_children(
                node, definition_ids, budget, class_node_types, memo
            )
        # if it's not a class, check if it's oversized. If not, make a definition chunk.
        size = node.end_byte - node.start_byte
        if size <= budget:
            return [(ChunkKind.DEFINITION, [node])]
        
        # if it's oversized, check if it has any nested definitions. If so, make a function skeleton chunk and go thru it's children.
        if any(_contains_definition(child, definition_ids, memo) for child in node.children):
            # oversized, but has a nested named def (e.g. a nested function) —
            # keep its signature as a skeleton to preserve its identity and namespace,
            # then recurse into its body.
            return [(ChunkKind.FUNCTION_SKELETON, [node])] + _walk_children(
                node, definition_ids, budget, class_node_types, memo
            )

        # oversized with nothing nested to split around — keep this as a real
        # definition chunk rather than demoting it to an anonymous leftover.
        # It'll exceed `budget`, but that's preferable to losing its name,
        # parent_symbol, and chunk_kind entirely.
        return [(ChunkKind.DEFINITION, [node])]
    
    # This node is not a captured definition.
    # If none of its descendants are definitions either, the whole subtree
    # becomes a leftover chunk.
    if not _contains_definition(node, definition_ids, memo):
        return [(ChunkKind.LEFTOVER, [node])]

    return _walk_children(node, definition_ids, budget, class_node_types, memo)


def _walk_children(
    node: Node,
    definition_ids: set[int],
    budget: int,
    class_node_types: set[str],
    memo: dict[int, bool],
) -> list[tuple[str, list[Node]]]:
    """Walk children and keep adjacent leftover nodes grouped together."""
    emitted: list[tuple[str, list[Node]]] = []
    leftover_buffer: list[Node] = []

    for child in node.children:
        for kind, nodes in _walk(child, definition_ids, budget, class_node_types, memo):
            if kind == ChunkKind.LEFTOVER:
                leftover_buffer.extend(nodes)
            else:
                if leftover_buffer:
                    emitted.append((ChunkKind.LEFTOVER, leftover_buffer))
                    leftover_buffer = []
                emitted.append((kind, nodes))

    if leftover_buffer:
        emitted.append((ChunkKind.LEFTOVER, leftover_buffer))
    return emitted


def walk_top_level(
    root: Node,
    definition_ids: set[int],
    budget: int,
    class_node_types: set[str],
) -> list[tuple[str, list[Node]]]:
    """Walk the root's children into ordered chunk candidates."""
    memo: dict[int, bool] = {}
    return _walk_children(root, definition_ids, budget, class_node_types, memo)