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
    enclosing_def_node: Node | None,
) -> list[tuple[str, list[Node], Node | None]]:
    """Classify a subtree as a definition, skeleton, leftover, or children.

    `enclosing_def_node` is the nearest ancestor definition node (class or
    oversized/skeletonized function) this subtree sits inside, or None at
    the top level. It's threaded through untouched and attached to every
    emitted candidate so the chunk factory (Step 6) can later resolve it to
    a parent_chunk_id -- this is what lets a LEFTOVER chunk (e.g. a class
    field) be linked back to the CLASS_SKELETON/FUNCTION_SKELETON chunk it
    came from, instead of losing that relationship entirely.
    """
    # If this node is a captured definition, it can be a real definition chunk,
    if node.id in definition_ids:
        if node.type in class_node_types:
            return [(ChunkKind.CLASS_SKELETON, [node], enclosing_def_node)] + _walk_children(
                node, definition_ids, budget, class_node_types, memo, node
            )

        size = node.end_byte - node.start_byte
        if size <= budget:
            return [(ChunkKind.DEFINITION, [node], enclosing_def_node)]

        if any(_contains_definition(child, definition_ids, memo) for child in node.children):
            # oversized, but has a nested named def (e.g. a nested function) —
            # keep its signature as a skeleton to preserve its identity and namespace,
            # then recurse into its body. `node` becomes the new enclosing definition
            # for anything found while recursing into it.
            return [(ChunkKind.FUNCTION_SKELETON, [node], enclosing_def_node)] + _walk_children(
                node, definition_ids, budget, class_node_types, memo, node
            )

        # oversized with nothing nested to split around — keep this as a real
        # definition chunk rather than demoting it to an anonymous leftover.
        # It'll exceed `budget`, but that's preferable to losing its name,
        # parent_symbol, and chunk_kind entirely.
        return [(ChunkKind.DEFINITION, [node], enclosing_def_node)]

    if not _contains_definition(node, definition_ids, memo):
        return [(ChunkKind.LEFTOVER, [node], enclosing_def_node)]

    return _walk_children(node, definition_ids, budget, class_node_types, memo, enclosing_def_node)


def _walk_children(
    node: Node,
    definition_ids: set[int],
    budget: int,
    class_node_types: set[str],
    memo: dict[int, bool],
    enclosing_def_node: Node | None,
) -> list[tuple[str, list[Node], Node | None]]:
    """Walk children and keep adjacent leftover nodes grouped together.

    All direct children share the same `enclosing_def_node` (their common
    parent), so buffered leftover nodes are always safe to bucket together
    under one parent reference.
    """
    emitted: list[tuple[str, list[Node], Node | None]] = []
    leftover_buffer: list[Node] = []

    for child in node.children:
        for kind, nodes, parent in _walk(
            child, definition_ids, budget, class_node_types, memo, enclosing_def_node
        ):
            if kind == ChunkKind.LEFTOVER:
                leftover_buffer.extend(nodes)
            else:
                if leftover_buffer:
                    emitted.append((ChunkKind.LEFTOVER, leftover_buffer, enclosing_def_node))
                    leftover_buffer = []
                emitted.append((kind, nodes, parent))

    if leftover_buffer:
        emitted.append((ChunkKind.LEFTOVER, leftover_buffer, enclosing_def_node))
    return emitted


def walk_top_level(
    root: Node,
    definition_ids: set[int],
    budget: int,
    class_node_types: set[str],
) -> list[tuple[str, list[Node], Node | None]]:
    """Walk the root's children into ordered chunk candidates.

    Each candidate is now a (kind, nodes, enclosing_def_node) triple instead
    of a (kind, nodes) pair -- the third element is None for every top-level
    candidate and the enclosing definition's own Node for anything nested
    inside a class or a skeletonized function.
    """
    memo: dict[int, bool] = {}
    return _walk_children(root, definition_ids, budget, class_node_types, memo, None)