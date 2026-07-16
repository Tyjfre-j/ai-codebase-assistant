from tree_sitter import Node

from app.core.constants import DEFAULT_CHUNK_BUDGET_CHARS
from app.core.exceptions import InvalidChunkBudgetError, MalformedSourceError
from app.ingestion.chunking.chunk_candidates import walk_top_level
from app.ingestion.chunking.chunk_factory import build_class_skeleton_chunk, build_definition_chunk
from app.ingestion.chunking.leftover_chunks import group_leftovers
from app.ingestion.chunking.query_captures import run_captures
from app.ingestion.code_chunk import ChunkKind, CodeChunk
from app.ingestion.languages import DEF_CAPTURES, LANG_HELPERS
from app.ingestion.source_parser import ParsedFile


def chunk_file(
    file_path: str, parsed: ParsedFile, budget: int = DEFAULT_CHUNK_BUDGET_CHARS
) -> tuple[list[CodeChunk], str, list[tuple[int, int]], dict[str, list[Node]]]:
    """Chunk one parsed file and return chunks, import metadata, and the raw captures.

    The captures dict is returned so callers (e.g. import-binding extraction) can
    reuse it instead of re-running the definitions query against the same parsed
    file a second time.
    """
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
    )

    definition_chunks: list[CodeChunk] = []
    leftover_groups: list[list[Node]] = []
    for candidate_kind, nodes in chunk_candidates:
        if candidate_kind == ChunkKind.DEFINITION:
            for node in nodes:
                definition_chunks.append(
                    build_definition_chunk(node, file_path, parsed, captures)
                )
        elif candidate_kind == ChunkKind.CLASS_SKELETON:
            definition_chunks.append(build_class_skeleton_chunk(nodes[0], file_path, parsed))
        else:
            leftover_groups.append(nodes)

    leftover_chunks, import_text, import_ranges = group_leftovers(
        leftover_groups, captures, file_path, parsed, budget
    )

    return definition_chunks + leftover_chunks, import_text, import_ranges, captures