from tree_sitter import Node

from app.core.constants import DEFAULT_CHUNK_BUDGET_CHARS
from app.core.exceptions import InvalidChunkBudgetError, MalformedSourceError
from app.ingestion.chunking.chunk_candidates import walk_top_level
from app.ingestion.chunking.chunk_factory import build_class_skeleton_chunk, build_definition_chunk, build_function_skeleton_chunk
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
    # Validate the chunk budget
    if budget <= 0:
        raise InvalidChunkBudgetError(f"budget must be positive, got {budget}")
    
    # Check for syntax errors in the parse tree. If there are errors, raise a MalformedSourceError.
    if parsed.tree.root_node.has_error:
        raise MalformedSourceError(
            f"{file_path} contains syntax errors — parse tree is unreliable, "
            f"refusing to chunk."
        )
    
    # Run the language query to get the captures for this file. This will return a dict mapping capture names to lists of nodes.
    # check app/ingestion/chunking/query_captures.py for details on what the captures output contains
    captures = run_captures(parsed)

    # Get the set of definition node IDs from the captures.
    # check app/ingestion/languages.py for details on what the DEF_CAPTURES constant contains
    definition_ids = {
        node.id
        for capture_name in DEF_CAPTURES
        for node in captures.get(capture_name, [])
    }
    
    # Get the language helpers for this file's language, and the set of class node types.
    # check app/ingestion/languages.py for details on what the LANG_HELPERS constant contains
    language_helpers = LANG_HELPERS[parsed.language]

    # Get the set of class node types for this language. This is used to determine whether a node is a class definition or not.
    class_node_types: set[str] = getattr(language_helpers, "CLASS_NODE_TYPES", set())

    # Walk the parse tree to classify nodes as definitions, skeletons, leftovers, or children.
    # check app/ingestion/chunking/chunk_candidates.py for details on what the walk_top_level function does
    # NOTE: each candidate is now a (kind, nodes, enclosing_def_node) triple — the third
    # element is the Node of the enclosing CLASS_SKELETON/FUNCTION_SKELETON this candidate
    # was found inside, or None at the top level. This is what lets a leftover chunk (e.g.
    # a class field) be linked back to the chunk it came from via parent_chunk_id below.
    chunk_candidates = walk_top_level(
        parsed.tree.root_node,
        definition_ids,
        budget,
        class_node_types,
    )
    
    # Build the actual CodeChunk objects from the classified nodes.
    definition_chunks: list[CodeChunk] = []
    leftover_groups: list[tuple[list[Node], Node | None]] = []
    # Tracks node.id -> chunk_id for every DEFINITION/CLASS_SKELETON/FUNCTION_SKELETON chunk
    # built so far in this file. walk_top_level always emits a candidate's enclosing definition
    # before anything nested inside it, so a parent is always already in this map by the time
    # one of its children needs to look it up.
    node_id_to_chunk_id: dict[int, str] = {}
    # depending on the candidate kind, build the appropriate chunk or group leftovers for later processing
    # check app/ingestion/chunking/chunk_factory.py for details on what each of the build_*_chunk functions do
    for candidate_kind, nodes, parent_node in chunk_candidates:
        # Resolve this candidate's enclosing definition (if any) to the chunk_id we already
        # built for it, so the chunk we're about to build can record parent_chunk_id.
        parent_chunk_id = (
            node_id_to_chunk_id.get(parent_node.id) if parent_node is not None else None
        )
        if candidate_kind == ChunkKind.DEFINITION:
            for node in nodes:
                # Build a definition chunk for each node and add it to the list of definition chunks.
                chunk = build_definition_chunk(node, file_path, parsed, captures, parent_chunk_id)
                definition_chunks.append(chunk)
                node_id_to_chunk_id[node.id] = chunk.chunk_id
        # Build a class skeleton chunk for each class node and add it to the list of definition chunks.
        elif candidate_kind == ChunkKind.CLASS_SKELETON:
            chunk = build_class_skeleton_chunk(nodes[0], file_path, parsed, parent_chunk_id)
            definition_chunks.append(chunk)
            node_id_to_chunk_id[nodes[0].id] = chunk.chunk_id
        # Build a function skeleton chunk for each function node and add it to the list of definition chunks.    
        elif candidate_kind == ChunkKind.FUNCTION_SKELETON:
            chunk = build_function_skeleton_chunk(nodes[0], file_path, parsed, captures, parent_chunk_id)
            definition_chunks.append(chunk)
            node_id_to_chunk_id[nodes[0].id] = chunk.chunk_id
        # Group leftover nodes together for later processing, alongside the enclosing definition
        # node (if any) so group_leftovers can resolve each group's parent_chunk_id once every
        # DEFINITION/CLASS_SKELETON/FUNCTION_SKELETON chunk in this file already has a chunk_id.
        # These will be combined into leftover chunks after all candidates have been processed.    
        else:
            leftover_groups.append((nodes, parent_node))

    leftover_chunks, import_text, import_ranges = group_leftovers(
        leftover_groups, captures, file_path, parsed, budget, node_id_to_chunk_id
    )

    return definition_chunks + leftover_chunks, import_text, import_ranges, captures