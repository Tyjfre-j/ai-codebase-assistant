from tree_sitter import Node

from app.core.constants import DEFAULT_CHUNK_BUDGET_CHARS
from app.core.exceptions import InvalidChunkBudgetError, MalformedSourceError
from app.ingestion.chunking.chunk_candidates import walk_top_level
from app.ingestion.chunking.chunk_factory import (
    build_class_skeleton_chunk,
    build_definition_chunk,
    build_file_overview_chunk,
    build_function_skeleton_chunk,
)
from app.ingestion.chunking.leftover_chunks import group_leftovers
from app.ingestion.chunking.query_captures import run_captures
from app.ingestion.code_chunk import ChunkKind, CodeChunk
from app.ingestion.languages import DEF_CAPTURES, LANG_HELPERS
from app.ingestion.source_parser import ParsedFile


def chunk_file(
    file_path: str, parsed: ParsedFile, budget: int = DEFAULT_CHUNK_BUDGET_CHARS
) -> tuple[list[CodeChunk], str, list[tuple[int, int]], dict[str, list[Node]]]:
    """Chunk one parsed file and return chunks, import metadata, and the raw captures."""
    if budget <= 0:
        raise InvalidChunkBudgetError(f"budget must be positive, got {budget}")

    if parsed.tree.root_node.has_error:
        raise MalformedSourceError(
            f"{file_path} contains syntax errors — parse tree is unreliable, "
            f"refusing to chunk."
        )

    captures = run_captures(parsed)

    definition_ids = {
        node.id
        for capture_name in DEF_CAPTURES
        for node in captures.get(capture_name, [])
    }

    language_helpers = LANG_HELPERS[parsed.language]
    class_node_types: set[str] = getattr(language_helpers, "CLASS_NODE_TYPES", set())

    chunk_candidates = walk_top_level(
        parsed.tree.root_node,
        definition_ids,
        budget,
        class_node_types,
        file_path,
    )

    definition_chunks: list[CodeChunk] = []
    leftover_groups: list[tuple[list[Node], Node | None]] = []
    node_id_to_chunk_id: dict[int, str] = {}
    top_level_names: list[str] = []

    for candidate_kind, nodes, parent_node, _scope_id in chunk_candidates:
        parent_chunk_id = (
            node_id_to_chunk_id.get(parent_node.id) if parent_node is not None else None
        )

        if candidate_kind == ChunkKind.DEFINITION:
            for node in nodes:
                chunk = build_definition_chunk(
                    node, file_path, parsed, captures, definition_ids, parent_chunk_id
                )
                definition_chunks.append(chunk)
                node_id_to_chunk_id[node.id] = chunk.chunk_id
                if parent_chunk_id is None:
                    top_level_names.append(chunk.full_name)

        elif candidate_kind == ChunkKind.CLASS_SKELETON:
            chunk = build_class_skeleton_chunk(
                nodes[0], file_path, parsed, captures, parent_chunk_id
            )
            definition_chunks.append(chunk)
            node_id_to_chunk_id[nodes[0].id] = chunk.chunk_id
            if parent_chunk_id is None:
                top_level_names.append(chunk.full_name)

        elif candidate_kind == ChunkKind.FUNCTION_SKELETON:
            chunk = build_function_skeleton_chunk(
                nodes[0], file_path, parsed, captures, parent_chunk_id
            )
            definition_chunks.append(chunk)
            node_id_to_chunk_id[nodes[0].id] = chunk.chunk_id
            if parent_chunk_id is None:
                top_level_names.append(chunk.full_name)

        else:
            leftover_groups.append((nodes, parent_node))

    leftover_chunks, import_text, import_ranges = group_leftovers(
        leftover_groups, captures, file_path, parsed, budget, node_id_to_chunk_id
    )

    overview_chunk = build_file_overview_chunk(
        parsed.tree.root_node, file_path, parsed, top_level_names, import_text
    )

    all_chunks = [overview_chunk] + definition_chunks + leftover_chunks
    return all_chunks, import_text, import_ranges, captures