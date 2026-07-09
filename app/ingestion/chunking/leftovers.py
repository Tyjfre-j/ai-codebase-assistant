from tree_sitter import Node

from app.ingestion.chunk_builder_helpers import node_text
from app.ingestion.chunk_model import CodeChunk
from app.ingestion.chunking.fields import build_leftover_chunk
from app.ingestion.languages import IMPORT_CAPTURE
from app.ingestion.parser import ParsedFile


def group_leftovers(
    leftover_groups: list[list[Node]],
    captures: dict[str, list[Node]],
    file_path: str,
    parsed: ParsedFile,
    budget: int,
) -> tuple[list[CodeChunk], str, list[tuple[int, int]]]:
    import_ids = {n.id for n in captures.get(IMPORT_CAPTURE, [])}

    imports: list[Node] = []
    grouped_chunks: list[CodeChunk] = []

    for group in leftover_groups:
        group_imports = [n for n in group if n.id in import_ids]
        group_other = [n for n in group if n.id not in import_ids]
        imports.extend(group_imports)

        buf: list[Node] = []
        buf_size = 0
        for n in group_other:
            n_size = n.end_byte - n.start_byte
            if buf and buf_size + n_size > budget:
                grouped_chunks.append(build_leftover_chunk(buf, file_path, parsed))
                buf, buf_size = [], 0
            buf.append(n)
            buf_size += n_size
        if buf:
            grouped_chunks.append(build_leftover_chunk(buf, file_path, parsed))

    import_text = "\n".join(node_text(n, parsed.content) for n in imports)
    import_ranges = [(n.start_byte, n.end_byte) for n in imports]

    return grouped_chunks, import_text, import_ranges