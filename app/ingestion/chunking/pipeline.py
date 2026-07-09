from tree_sitter import Node
from app.ingestion.chunk_model import CodeChunk
from app.ingestion.chunking.captures import run_captures
from app.ingestion.chunking.fields import build_chunk, build_class_skeleton_chunk
from app.ingestion.chunking.leftovers import group_leftovers
from app.ingestion.chunking.merger import merge_adjacent_defs
from app.ingestion.chunking.splitter import walk_top_level
from app.ingestion.languages import DEF_CAPTURES
from app.ingestion.parser import ParsedFile


def chunk_file(
    file_path: str, parsed: ParsedFile, budget: int = 1500
) -> tuple[list[CodeChunk], str, list[tuple[int, int]]]:
    captures = run_captures(parsed)
    definition_ids = {n.id for cap in DEF_CAPTURES for n in captures.get(cap, [])}

    walked = walk_top_level(parsed.tree.root_node, definition_ids, budget)

    def_chunks: list[CodeChunk] = []
    leftover_groups: list[list[Node]] = []
    for kind, nodes in walked:
        if kind == "def":
            for n in nodes:
                def_chunks.append(build_chunk(n, "definition", file_path, parsed, captures))
        elif kind == "class_skeleton":
            def_chunks.append(build_class_skeleton_chunk(nodes[0], file_path, parsed))
        else:
            leftover_groups.append(nodes)

    def_chunks = merge_adjacent_defs(def_chunks, budget)
    leftover_chunks, import_text, import_ranges = group_leftovers(
        leftover_groups, captures, file_path, parsed, budget
    )

    return def_chunks + leftover_chunks, import_text, import_ranges