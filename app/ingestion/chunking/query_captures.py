from collections import defaultdict

from tree_sitter import Node, QueryCursor

from app.core.exceptions import UnregisteredLanguageError
from app.ingestion.languages import DEF_CAPTURES, LANG_HELPERS
from app.ingestion.source_parser import ParsedFile


def run_captures(parsed: ParsedFile) -> dict[str, list[Node]]:
    """Run the language query and normalize captures by capture name."""
    if parsed.language not in LANG_HELPERS:
        raise UnregisteredLanguageError(
            f"No LANG_HELPERS entry for language {parsed.language!r}. "
            f"Known languages: {sorted(LANG_HELPERS)}"
        )
    language_helpers = LANG_HELPERS[parsed.language]

    cursor = QueryCursor(parsed.query)
    raw_captures = cursor.captures(parsed.tree.root_node)

    captures_by_name: dict[str, list[Node]] = defaultdict(list)
    if isinstance(raw_captures, dict):
        for capture_name, nodes in raw_captures.items():
            captures_by_name[capture_name].extend(nodes)
    else:
        for node, capture_name in raw_captures:
            captures_by_name[capture_name].append(node)

    for definition_capture in DEF_CAPTURES:
        if definition_capture not in captures_by_name:
            continue
        resolved_nodes = [
            language_helpers.unwrap_decorated_definition_node(node)
            for node in captures_by_name[definition_capture]
        ]
        seen: set[int] = set()
        unique_nodes: list[Node] = []
        for node in resolved_nodes:
            if node.id not in seen:
                seen.add(node.id)
                unique_nodes.append(node)
        captures_by_name[definition_capture] = unique_nodes

    return captures_by_name
