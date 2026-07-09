from tree_sitter import Node


def _contains_definition(node: Node, definition_ids: set[int]) -> bool:
    if node.id in definition_ids:
        return True
    return any(_contains_definition(child, definition_ids) for child in node.children)


def _walk(node: Node, definition_ids: set[int], budget: int) -> list[tuple[str, list[Node]]]:
    if node.id in definition_ids:
        size = node.end_byte - node.start_byte
        if size <= budget:
            return [("def", [node])]

        if node.type == "class_definition":
            return [("class_skeleton", [node])] + _walk_children(node, definition_ids, budget)

        return _walk_children(node, definition_ids, budget)

    if not _contains_definition(node, definition_ids):
        return [("leftover", [node])]

    return _walk_children(node, definition_ids, budget)


def _walk_children(node: Node, definition_ids: set[int], budget: int) -> list[tuple[str, list[Node]]]:
    emitted: list[tuple[str, list[Node]]] = []
    leftover_buffer: list[Node] = []

    for child in node.children:
        for kind, nodes in _walk(child, definition_ids, budget):
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


def walk_top_level(root: Node, definition_ids: set[int], budget: int) -> list[tuple[str, list[Node]]]:
    return _walk_children(root, definition_ids, budget)