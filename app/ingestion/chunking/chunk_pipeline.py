from tree_sitter import Node

from app.core.exceptions import InvalidChunkBudgetError, MalformedSourceError
from app.ingestion.chunking.chunk_candidates import walk_top_level
from app.ingestion.chunking.chunk_factory import build_chunk, build_class_skeleton_chunk
from app.ingestion.chunking.definition_merger import merge_adjacent_defs
from app.ingestion.chunking.leftover_chunks import group_leftovers
from app.ingestion.chunking.query_captures import run_captures
from app.ingestion.code_chunk import CodeChunk
from app.ingestion.languages import DEF_CAPTURES, LANG_HELPERS
from app.ingestion.source_parser import ParsedFile


def chunk_file(
    file_path: str, parsed: ParsedFile, budget: int = 1500
) -> tuple[list[CodeChunk], str, list[tuple[int, int]]]:
    """Chunk one parsed file and return chunks plus extracted import metadata."""
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
        if candidate_kind == "def":
            for node in nodes:
                definition_chunks.append(
                    build_chunk(node, "definition", file_path, parsed, captures)
                )
        elif candidate_kind == "class_skeleton":
            definition_chunks.append(build_class_skeleton_chunk(nodes[0], file_path, parsed))
        else:
            leftover_groups.append(nodes)

    definition_chunks = merge_adjacent_defs(definition_chunks, budget)
    leftover_chunks, import_text, import_ranges = group_leftovers(
        leftover_groups, captures, file_path, parsed, budget
    )

    return definition_chunks + leftover_chunks, import_text, import_ranges
