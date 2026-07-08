"""Builds CodeChunk objects from tree-sitter query matches."""

import hashlib

from tree_sitter import QueryCursor

from app.core.exceptions import ChunkExtractionError
from app.ingestion.chunk_model import ChunkType, CodeChunk

_CLASS_NODE_TYPES = {"class_definition", "class_declaration", "type_declaration"}


def node_text(node, content: bytes) -> str:
    """Extract the source text a node spans, from the original file bytes."""
    return content[node.start_byte:node.end_byte].decode("utf-8")


def node_lines(node) -> tuple[int, int]:
    """Return (start_line, end_line), 1-indexed, from a node's 0-indexed points."""
    return node.start_point[0] + 1, node.end_point[0] + 1


def make_chunk_id(file_path: str, start_line: int, end_line: int) -> str:
    """A stable id — re-parsing the same file produces the same ids."""
    raw = f"{file_path}:{start_line}:{end_line}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def find_enclosing_class(node, content: bytes) -> str | None:
    """Walk up from a function/method node to find its enclosing class name, if any."""
    current = node.parent
    while current is not None:
        if current.type in _CLASS_NODE_TYPES:
            name_node = current.child_by_field_name("name")
            return node_text(name_node, content) if name_node is not None else None
        current = current.parent
    return None


def extract_param_names(params_node, content: bytes) -> tuple[str, ...]:
    """Pull each parameter's text from a parameter-list node's named children."""
    return tuple(node_text(child, content) for child in params_node.named_children)


def resolve_bound_name(module: str, bound_name: str | None, alias: str | None) -> str:
    """The identifier this import actually binds into local scope."""
    if alias is not None:
        return alias
    if bound_name is not None:
        return bound_name
    return module.rsplit(".", 1)[-1].rsplit("/", 1)[-1]


def build_function_chunk(captures: dict, content: bytes, file_path: str, language: str) -> CodeChunk:
    def_node = captures["func.def"][0]
    name_node = captures["func.name"][0]
    params_node = captures["func.params"][0] if "func.params" in captures else None

    start_line, end_line = node_lines(def_node)
    parent_class = find_enclosing_class(def_node, content)
    chunk_type = ChunkType.METHOD if parent_class is not None else ChunkType.FUNCTION
    parameters = extract_param_names(params_node, content) if params_node is not None else ()

    return CodeChunk(
        chunk_id=make_chunk_id(file_path, start_line, end_line),
        file_path=file_path,
        language=language,
        chunk_type=chunk_type,
        qualified_name=node_text(name_node, content),
        parameters=parameters,
        parent_class=parent_class,
        imports=(),
        source_code=node_text(def_node, content),
        start_line=start_line,
        end_line=end_line,
    )


def build_class_chunk(captures: dict, content: bytes, file_path: str, language: str) -> CodeChunk:
    def_node = captures["class.def"][0]
    name_node = captures["class.name"][0]

    start_line, end_line = node_lines(def_node)

    return CodeChunk(
        chunk_id=make_chunk_id(file_path, start_line, end_line),
        file_path=file_path,
        language=language,
        chunk_type=ChunkType.CLASS,
        qualified_name=node_text(name_node, content),
        parameters=(),
        parent_class=None,
        imports=(),
        source_code=node_text(def_node, content),
        start_line=start_line,
        end_line=end_line,
    )


def build_import_chunk(captures: dict, content: bytes, file_path: str, language: str) -> CodeChunk:
    stmt_node = captures["import.stmt"][0]
    module = node_text(captures["import.module"][0], content) if "import.module" in captures else ""
    bound_name = node_text(captures["import.bound_name"][0], content) if "import.bound_name" in captures else None
    alias = node_text(captures["import.alias"][0], content) if "import.alias" in captures else None

    resolved_name = resolve_bound_name(module, bound_name, alias)
    start_line, end_line = node_lines(stmt_node)

    return CodeChunk(
        chunk_id=make_chunk_id(file_path, start_line, end_line),
        file_path=file_path,
        language=language,
        chunk_type=ChunkType.IMPORT,
        qualified_name=resolved_name,
        parameters=(),
        parent_class=None,
        imports=(module,),
        source_code=node_text(stmt_node, content),
        start_line=start_line,
        end_line=end_line,
    )


def _get_covered_ranges(chunks: list[CodeChunk]) -> list[tuple[int, int]]:
    return [(c.start_line, c.end_line) for c in chunks]


def _is_covered(node, covered_ranges: list[tuple[int, int]]) -> bool:
    start, end = node_lines(node)
    return any(cs <= start and end <= ce for cs, ce in covered_ranges)


def build_leftover_chunks(
    root_node, chunks: list[CodeChunk], content: bytes, file_path: str, language: str
) -> list[CodeChunk]:
    """Wrap top-level statements not covered by any real chunk into module-level chunks."""
    covered = _get_covered_ranges(chunks)
    leftover_chunks: list[CodeChunk] = []
    current_group = []

    def flush_group():
        if not current_group:
            return
        start_line, _ = node_lines(current_group[0])
        _, end_line = node_lines(current_group[-1])
        node_types = sorted({n.type for n in current_group})
        source = content[current_group[0].start_byte:current_group[-1].end_byte].decode("utf-8")

        leftover_chunks.append(CodeChunk(
            chunk_id=make_chunk_id(file_path, start_line, end_line),
            file_path=file_path,
            language=language,
            chunk_type=ChunkType.MODULE_LEVEL,
            qualified_name=f"module-level ({', '.join(node_types)})",
            parameters=(),
            parent_class=None,
            imports=(),
            source_code=source,
            start_line=start_line,
            end_line=end_line,
        ))

    for child in root_node.named_children:
        if _is_covered(child, covered):
            flush_group()
            current_group = []
        else:
            current_group.append(child)
    flush_group()

    return leftover_chunks


def build_chunks(tree, query, content: bytes, file_path: str, language: str) -> list[CodeChunk]:
    """Run the query against a parsed tree and build CodeChunk objects from the matches,
    then wrap any uncovered top-level statements into module-level chunks."""
    cursor = QueryCursor(query)
    matches = cursor.matches(tree.root_node)

    chunks: list[CodeChunk] = []
    for _pattern_index, captures in matches:
        try:
            if "func.def" in captures:
                chunks.append(build_function_chunk(captures, content, file_path, language))
            elif "class.def" in captures:
                chunks.append(build_class_chunk(captures, content, file_path, language))
            elif "import.stmt" in captures:
                chunks.append(build_import_chunk(captures, content, file_path, language))
        except (KeyError, ValueError) as e:
            raise ChunkExtractionError(f"Failed to build chunk in {file_path}: {e}") from e

    chunks.extend(build_leftover_chunks(tree.root_node, chunks, content, file_path, language))
    return chunks