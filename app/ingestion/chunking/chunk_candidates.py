from tree_sitter import Node


def _contains_definition(node: Node, definition_ids: set[int]) -> bool:
    """Return whether this node or any descendant is a captured definition."""
    if node.id in definition_ids:
        return True
    return any(_contains_definition(child, definition_ids) for child in node.children)


def _walk(
    node: Node,
    definition_ids: set[int],
    budget: int,
    class_node_types: set[str],
) -> list[tuple[str, list[Node]]]:
    """Classify a subtree as a definition, skeleton, leftover, or children."""
    if node.id in definition_ids:
        if node.type in class_node_types:
            # Classes always get a skeleton + recurse into children, regardless
            # of size, so methods are always individually chunked.
            return [("class_skeleton", [node])] + _walk_children(
                node, definition_ids, budget, class_node_types
            )

        size = node.end_byte - node.start_byte
        if size <= budget:
            return [("def", [node])]

        if _contains_definition(node, definition_ids):
            # oversized, but has a nested named def (e.g. a nested function) —
            # recurse to find it instead of losing this node's identity
            return _walk_children(node, definition_ids, budget, class_node_types)

        # oversized with nothing nested to split around — keep this as a real
        # definition chunk rather than demoting it to an anonymous leftover.
        # It'll exceed `budget`, but that's preferable to losing its name,
        # parent_symbol, and chunk_kind entirely.
        return [("def", [node])]

    if not _contains_definition(node, definition_ids):
        return [("leftover", [node])]

    return _walk_children(node, definition_ids, budget, class_node_types)
def _walk_children(
    node: Node,
    definition_ids: set[int],
    budget: int,
    class_node_types: set[str],
) -> list[tuple[str, list[Node]]]:
    """Walk children and keep adjacent leftover nodes grouped together."""
    emitted: list[tuple[str, list[Node]]] = []
    leftover_buffer: list[Node] = []

    for child in node.children:
        for kind, nodes in _walk(child, definition_ids, budget, class_node_types):
            if kind == "leftover":
                leftover_buffer.extend(nodes)
            else:
                if leftover_buffer:
                    emitted.append(("leftover", leftover_buffer))
                    leftover_buffer = []
                emitted.append((kind, nodes))

    if leftover_buffer:
        emitted.append(("leftover", leftover_buffer))
    return emitted


def walk_top_level(
    root: Node,
    definition_ids: set[int],
    budget: int,
    class_node_types: set[str],
) -> list[tuple[str, list[Node]]]:
    """Walk the root's children into ordered chunk candidates."""
    return _walk_children(root, definition_ids, budget, class_node_types)
