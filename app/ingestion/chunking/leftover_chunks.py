from tree_sitter import Node

from app.ingestion.chunking.chunk_factory import build_leftover_code_chunk
from app.ingestion.code_chunk import CodeChunk
from app.ingestion.languages import IMPORT_CAPTURE
from app.ingestion.source_parser import ParsedFile
from app.ingestion.source_text import node_text


def group_leftovers(
    leftover_groups: list[list[Node]],
    captures: dict[str, list[Node]],
    file_path: str,
    parsed: ParsedFile,
    budget: int,
) -> tuple[list[CodeChunk], str, list[tuple[int, int]]]:
    """Split leftover nodes into import metadata and budgeted chunks."""
    import_ids = {node.id for node in captures.get(IMPORT_CAPTURE, [])}

    imports: list[Node] = []
    leftover_chunks: list[CodeChunk] = []

    for group in leftover_groups:
        imports.extend(node for node in group if node.id in import_ids)
        segments: list[list[Node]] = []
        current_segment: list[Node] = []
        for node in group:
            if node.id in import_ids:
                if current_segment:
                    segments.append(current_segment)
                    current_segment = []
                continue
            current_segment.append(node)
        if current_segment:
            segments.append(current_segment)

        chunk_buffer: list[list[Node]] = []
        buffer_size = 0
        for segment in segments:
            segment_size = segment[-1].end_byte - segment[0].start_byte
            if chunk_buffer and buffer_size + segment_size > budget:
                leftover_chunks.append(build_leftover_code_chunk(chunk_buffer, file_path, parsed))
                chunk_buffer, buffer_size = [], 0
            chunk_buffer.append(segment)
            buffer_size += segment_size
        if chunk_buffer:
            leftover_chunks.append(build_leftover_code_chunk(chunk_buffer, file_path, parsed))

    import_text = "\n".join(node_text(node, parsed.content) for node in imports)
    import_ranges = [(node.start_byte, node.end_byte) for node in imports]

    return leftover_chunks, import_text, import_ranges