"""Builds CodeChunk objects from tree-sitter query matches, for any supported language."""

import logging

from tree_sitter import QueryCursor

from app.ingestion.chunk_model import ChunkType, CodeChunk
from app.ingestion.chunk_builder_helpers import (
    build_file_summary_chunk,
    build_leftover_chunks,
    build_type_skeleton,
    extract_module_docstring,
    extract_param_names,
    filter_trivial_nested_chunks,
    find_enclosing_type,
    make_chunk_id,
    node_lines,
    node_text,
    resolve_bound_name,
)

logger = logging.getLogger(__name__)


def build_function_chunk(captures: dict, content: bytes, file_path: str, language: str, lang_module) -> CodeChunk:
    raw_def_node = captures["func.def"][0]
    def_node = lang_module.resolve_definition_node(raw_def_node)
    name_node = captures["func.name"][0]
    params_node = captures["func.params"][0] if "func.params" in captures else None

    start_line, end_line = node_lines(def_node)

    if language == "go":
        parent_class = lang_module.resolve_parent_class(captures, content)
    else:
        parent_class = find_enclosing_type(raw_def_node, content, lang_module.CLASS_NODE_TYPES)

    chunk_type = ChunkType.METHOD if parent_class is not None else ChunkType.FUNCTION
    parameters = extract_param_names(params_node, content)

    name = node_text(name_node, content)
    qualified_name = f"{parent_class}.{name}" if parent_class else name
    source_code = node_text(def_node, content)

    return CodeChunk(
        chunk_id=make_chunk_id(file_path, qualified_name, source_code),
        file_path=file_path,
        language=language,
        chunk_type=chunk_type,
        qualified_name=qualified_name,
        parameters=parameters,
        parent_class=parent_class,
        imports=(),
        source_code=source_code,
        start_line=start_line,
        end_line=end_line,
    )


def build_class_chunk(captures: dict, content: bytes, file_path: str, language: str, lang_module) -> CodeChunk:
    raw_def_node = captures["class.def"][0]
    def_node = lang_module.resolve_definition_node(raw_def_node)
    name_node = captures["class.name"][0]

    start_line, end_line = node_lines(def_node)
    qualified_name = node_text(name_node, content)
    source_code = build_type_skeleton(
        raw_def_node, content, lang_module.CLASS_NODE_TYPES, lang_module.get_member_info
    )

    return CodeChunk(
        chunk_id=make_chunk_id(file_path, qualified_name, source_code),
        file_path=file_path,
        language=language,
        chunk_type=ChunkType.CLASS,
        qualified_name=qualified_name,
        parameters=(),
        parent_class=None,
        imports=(),
        source_code=source_code,
        start_line=start_line,
        end_line=end_line,
    )


def _resolve_import_names(captures_list: list[dict], content: bytes) -> list[str]:
    names = []
    for captures in captures_list:
        module = node_text(captures["import.module"][0], content) if "import.module" in captures else ""
        bound_name = node_text(captures["import.bound_name"][0], content) if "import.bound_name" in captures else None
        alias = node_text(captures["import.alias"][0], content) if "import.alias" in captures else None
        names.append(resolve_bound_name(module, bound_name, alias))
    return names


def _group_matches_by_anchor(matches, anchor_key: str) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for _pattern_idx, captures in matches:
        if anchor_key not in captures:
            continue
        anchor_id = captures[anchor_key][0].id
        grouped.setdefault(anchor_id, []).append(captures)
    return grouped


def build_chunks(tree, query, content: bytes, file_path: str, language: str, lang_module) -> list[CodeChunk]:
    """Run the query, build chunks, resolve imports, add leftovers and a file summary.

    lang_module is one of python_lang / javascript_lang / typescript_lang / go_lang —
    whichever matches `language` for this file.
    """
    cursor = QueryCursor(query)
    matches = cursor.matches(tree.root_node)

    func_class_chunks: list[CodeChunk] = []
    for _pattern_index, captures in matches:
        try:
            if "func.def" in captures:
                func_class_chunks.append(
                    build_function_chunk(captures, content, file_path, language, lang_module)
                )
            elif "class.def" in captures:
                func_class_chunks.append(
                    build_class_chunk(captures, content, file_path, language, lang_module)
                )
        except (KeyError, ValueError) as e:
            logger.warning("Skipping malformed chunk in %s: %s", file_path, e)
            continue

    func_class_chunks = filter_trivial_nested_chunks(func_class_chunks)

    import_groups = _group_matches_by_anchor(matches, "import.stmt")
    resolved_imports: list[str] = []
    for _anchor_id, captures_list in import_groups.items():
        try:
            resolved_imports.extend(_resolve_import_names(captures_list, content))
        except (KeyError, ValueError) as e:
            logger.warning("Skipping malformed import in %s: %s", file_path, e)
            continue

    leftover_chunks = build_leftover_chunks(tree.root_node, func_class_chunks, content, file_path, language)
    chunks = func_class_chunks + leftover_chunks

    docstring = extract_module_docstring(tree.root_node, content) if language == "python" else None
    top_level_symbols = [c.qualified_name for c in func_class_chunks if c.parent_class is None]
    dedup_imports = tuple(dict.fromkeys(resolved_imports))

    chunks.append(build_file_summary_chunk(
        docstring, dedup_imports, top_level_symbols, content, file_path, language
    ))

    return chunks