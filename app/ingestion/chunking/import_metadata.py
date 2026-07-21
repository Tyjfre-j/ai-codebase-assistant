from tree_sitter import Node

from app.ingestion.languages import IMPORT_CAPTURE
from app.ingestion.source_parser import ParsedFile
from app.ingestion.source_text import node_text


def extract_import_metadata(
    captures: dict[str, list[Node]], parsed: ParsedFile
) -> tuple[str, list[tuple[int, int]]]:
    """Extract import statement text and byte ranges from the file's captures."""
    import_nodes = captures.get(IMPORT_CAPTURE, [])
    import_text = "\n".join(node_text(node, parsed.content) for node in import_nodes)
    import_ranges = [(node.start_byte, node.end_byte) for node in import_nodes]
    return import_text, import_ranges