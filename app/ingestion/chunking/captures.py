from collections import defaultdict

from tree_sitter import Node, QueryCursor

from app.ingestion.languages import DEF_CAPTURES, LANG_HELPERS
from app.ingestion.parser import ParsedFile


def run_captures(parsed: ParsedFile) -> dict[str, list[Node]]:
    helpers = LANG_HELPERS[parsed.language]

    cursor = QueryCursor(parsed.query)
    raw = cursor.captures(parsed.tree.root_node)

    grouped: dict[str, list[Node]] = defaultdict(list)
    if isinstance(raw, dict):
        for name, nodes in raw.items():
            grouped[name].extend(nodes)
    else:
        for node, name in raw:
            grouped[name].append(node)

    for cap in DEF_CAPTURES:
        if cap not in grouped:
            continue
        resolved = [helpers.resolve_definition_node(n) for n in grouped[cap]]
        seen: set[int] = set()
        deduped = []
        for n in resolved:
            if n.id not in seen:
                seen.add(n.id)
                deduped.append(n)
        grouped[cap] = deduped

    return grouped