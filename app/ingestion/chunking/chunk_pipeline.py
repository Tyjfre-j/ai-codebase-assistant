from tree_sitter import Node

from app.core.constants import (
    DEFAULT_CHUNK_INCLUSION_BUDGET_CHARS,
    DEFAULT_FILE_SKELETON_THRESHOLD_CHARS,
)
from app.core.exceptions import InvalidChunkBudgetError, MalformedSourceError
from app.ingestion.chunking.chunk_candidates import walk_top_level
from app.ingestion.chunking.chunk_factory import (
    build_class_skeleton_chunk,
    build_definition_chunk,
    build_file_skeleton_chunk,
    build_function_skeleton_chunk,
)
from app.ingestion.chunking.import_metadata import extract_import_metadata
from app.ingestion.chunking.query_captures import run_captures
from app.ingestion.code_chunk import ChunkKind, CodeChunk
from app.ingestion.languages import DEF_CAPTURES, IMPORT_CAPTURE
from app.ingestion.source_parser import ParsedFile


def chunk_file(
    file_path: str,
    parsed: ParsedFile,
    budget: int = DEFAULT_CHUNK_INCLUSION_BUDGET_CHARS,
    skeleton_threshold: int = DEFAULT_FILE_SKELETON_THRESHOLD_CHARS,
) -> tuple[list[CodeChunk], str, list[tuple[int, int]], dict[str, list[Node]]]:
    """Chunk one parsed file and return chunks, import metadata, and the raw captures."""

    if budget <= 0:
        raise InvalidChunkBudgetError(f"budget must be positive, got {budget}")
    
    if skeleton_threshold <= 0:
        raise InvalidChunkBudgetError(
            f"skeleton_threshold must be positive, got {skeleton_threshold}"
        )

    if parsed.tree.root_node.has_error:
        raise MalformedSourceError(
            f"{file_path} contains syntax errors — parse tree is unreliable, "
            f"refusing to chunk."
        )

    captures = run_captures(parsed)

    definition_ids: set[int] = set()
    definition_kind_by_id: dict[int, str] = {}

    for capture_name in DEF_CAPTURES:
        for node in captures.get(capture_name, []):
            definition_ids.add(node.id)
            definition_kind_by_id[node.id] = capture_name
    
    import_ids = {node.id for node in captures.get(IMPORT_CAPTURE, [])}

    import_text, import_ranges = extract_import_metadata(captures, parsed)

    root = parsed.tree.root_node

    file_size = len(parsed.content)
    build_skeleton = file_size > skeleton_threshold

    definition_chunks: list[CodeChunk] = []
    node_id_to_chunk_id: dict[int, str] = {}
    file_skeleton_chunk_id: str | None = None

    if build_skeleton:
        file_skeleton = build_file_skeleton_chunk(
            root, file_path, parsed, definition_ids, definition_kind_by_id, import_ids
        )
        definition_chunks.append(file_skeleton)
        node_id_to_chunk_id[root.id] = file_skeleton.chunk_id
        file_skeleton_chunk_id = file_skeleton.chunk_id

    chunk_candidates = walk_top_level(
        root, definition_ids, definition_kind_by_id, budget, file_path,
    )

    for candidate_kind, nodes, parent_node in chunk_candidates:
        if parent_node is not None:
            parent_chunk_id = node_id_to_chunk_id.get(parent_node.id)
        else:
            parent_chunk_id = file_skeleton_chunk_id

        if candidate_kind == ChunkKind.DEFINITION:
            for node in nodes:
                chunk = build_definition_chunk(
                    node, file_path, parsed, captures, definition_ids, parent_chunk_id
                )
                definition_chunks.append(chunk)
                node_id_to_chunk_id[node.id] = chunk.chunk_id

        elif candidate_kind == ChunkKind.CLASS_SKELETON:
            chunk = build_class_skeleton_chunk(
                nodes[0], file_path, parsed, captures, definition_ids, parent_chunk_id
            )
            definition_chunks.append(chunk)
            node_id_to_chunk_id[nodes[0].id] = chunk.chunk_id

        elif candidate_kind == ChunkKind.FUNCTION_SKELETON:
            chunk = build_function_skeleton_chunk(
                nodes[0], file_path, parsed, captures, definition_ids, parent_chunk_id
            )
            definition_chunks.append(chunk)
            node_id_to_chunk_id[nodes[0].id] = chunk.chunk_id

    return definition_chunks, import_text, import_ranges, captures