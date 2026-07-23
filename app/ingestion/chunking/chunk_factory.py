from tree_sitter import Node

from app.ingestion.code_chunk import ChunkKind, CodeChunk
from app.ingestion.languages import LANG_HELPERS
from app.ingestion.refs.extractor import extract_reference_records
from app.ingestion.source_parser import ParsedFile
from app.ingestion.source_text import node_text, stable_chunk_id


def _collect_contained_symbols(
    node: Node,
    definition_ids: set[int],
    language_helpers,
    parsed: ParsedFile,
    captures: dict[str, list[Node]],
) -> list[str]:
    """Full names of nested captured definitions inside `node` that were folded into this
    chunk's code rather than emitted as their own chunk. `node` itself is excluded."""
    contained: list[str] = []

    def _walk(n: Node, is_root: bool) -> None:
        if not is_root and n.id in definition_ids:
            defined_in_class = language_helpers.get_enclosing_class_name(n, parsed.content)
            name = language_helpers.get_definition_name(n, parsed.content)
            namespace = language_helpers.get_ancestor_namespace(n, captures, parsed.content)
            if namespace:
                full_name = ".".join(namespace + [name])
            elif defined_in_class:
                full_name = f"{defined_in_class}.{name}"
            else:
                full_name = name
            contained.append(full_name)
        for child in n.children:
            _walk(child, False)

    _walk(node, True)
    return contained


def _filter_out_nested_refs(node: Node, definition_ids: set[int], all_refs: list) -> list:
    """Keep only refs whose site is NOT inside a nested captured definition"""
    nested_ranges: list[tuple[int, int]] = []

    def _collect(n: Node, is_root: bool) -> None:
        if not is_root and n.id in definition_ids:
            nested_ranges.append((n.start_byte, n.end_byte))
        for child in n.children:
            _collect(child, False)

    _collect(node, True)

    def _is_nested(ref) -> bool:
        return any(
            nr_start <= ref.start_byte and ref.end_byte <= nr_end
            for nr_start, nr_end in nested_ranges
        )

    return [ref for ref in all_refs if not _is_nested(ref)]


def _render_body_lines(
    body: Node,
    definition_ids: set[int],
    language_helpers,
    parsed: ParsedFile,
    exclude_ids: set[int] | None = None,
) -> list[str]:
    """Shared by definition skeletons and file skeletons: one line per direct child —
    a signature stub for anything that got its own chunk, verbatim text otherwise."""
    get_sig = language_helpers.get_signature_text
    exclude_ids = exclude_ids or set()
    lines: list[str] = []
    for child in body.children:
        if child.id in exclude_ids:
            continue
        if child.id in definition_ids:
            stub = get_sig(child, parsed.content)
            lines.append(f"{stub}..." if stub is not None else node_text(child, parsed.content).strip())
            continue
        text = node_text(child, parsed.content).strip()
        if text:
            lines.append(text)
    return lines


def build_definition_chunk(
    node: Node,
    file_path: str,
    parsed: ParsedFile,
    captures: dict[str, list[Node]],
    definition_ids: set[int],
    parent_chunk_id: str | None = None,
) -> CodeChunk:
    """Build a CodeChunk for a captured definition node kept in full (fits budget)."""
    language_helpers = LANG_HELPERS[parsed.language]
    defined_in_class = language_helpers.get_enclosing_class_name(node, parsed.content)
    name = language_helpers.get_definition_name(node, parsed.content)

    namespace = language_helpers.get_ancestor_namespace(node, captures, parsed.content)
    if namespace:
        full_name = ".".join(namespace + [name])
    elif defined_in_class:
        full_name = f"{defined_in_class}.{name}"
    else:
        full_name = name

    code = node_text(node, parsed.content)
    references = extract_reference_records(node, parsed.content, parsed.ref_query)
    contained_symbols = _collect_contained_symbols(
        node, definition_ids, language_helpers, parsed, captures
    )

    resolved_type = language_helpers.get_actual_definition_type(node)

    return CodeChunk(
        chunk_id=stable_chunk_id(file_path, node.start_byte, full_name),
        full_name=full_name,
        name=name,
        defined_in_class=defined_in_class,
        file_path=file_path,
        start_byte=node.start_byte,
        end_byte=node.end_byte,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        language=parsed.language,
        code=code,
        node_type=resolved_type,
        kind=ChunkKind.DEFINITION,
        size_chars=len(code),
        references=references,
        parent_chunk_id=parent_chunk_id,
        contained_symbols=contained_symbols,
    )


def build_skeleton_chunk(
    node: Node,
    file_path: str,
    parsed: ParsedFile,
    captures: dict[str, list[Node]],
    definition_ids: set[int],
    parent_chunk_id: str | None = None,
) -> CodeChunk:
    """Build a skeleton chunk for any oversized definition — class, function, or interface.
    Signature line, then one line per direct body child: a stub for anything that got
    its own chunk, verbatim text for everything else."""
    language_helpers = LANG_HELPERS[parsed.language]
    actual = language_helpers.get_actual_definition_node(node)
    defined_in_class = language_helpers.get_enclosing_class_name(node, parsed.content)
    name = language_helpers.get_definition_name(node, parsed.content)

    namespace = language_helpers.get_ancestor_namespace(node, captures, parsed.content)
    if namespace:
        full_name = ".".join(namespace + [name])
    elif defined_in_class:
        full_name = f"{defined_in_class}.{name}"
    else:
        full_name = name

    header = language_helpers.get_signature_text(node, parsed.content)
    if header is None:
        header = node_text(node, parsed.content)

    body = language_helpers.get_node_body(actual)
    lines = [header]
    if body is not None:
        member_lines = _render_body_lines(body, definition_ids, language_helpers, parsed)
        if member_lines:
            lines.extend(f"    {line}" for line in member_lines)
        else:
            lines.append("    ...")
    else:
        lines[0] = header + "..."

    footer = language_helpers.get_class_footer()
    if footer is not None:
        lines.append(footer)

    code = "\n".join(lines)

    all_refs = extract_reference_records(node, parsed.content, parsed.ref_query)
    references = _filter_out_nested_refs(node, definition_ids, all_refs)

    resolved_type = language_helpers.get_actual_definition_type(node)

    return CodeChunk(
        chunk_id=stable_chunk_id(file_path, node.start_byte, full_name),
        full_name=full_name,
        name=name,
        defined_in_class=defined_in_class,
        file_path=file_path,
        start_byte=node.start_byte,
        end_byte=node.end_byte,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        language=parsed.language,
        code=code,
        node_type=resolved_type,
        kind=ChunkKind.DEFINITION_SKELETON,
        size_chars=len(code),
        references=references,
        parent_chunk_id=parent_chunk_id,
    )


def build_file_skeleton_chunk(
    root: Node,
    file_path: str,
    parsed: ParsedFile,
    definition_ids: set[int],
    import_ids: set[int],
) -> CodeChunk:
    """Build a compact file chunk: all top-level non-definition, non-import content
    verbatim, plus one signature line per top-level definition."""
    language_helpers = LANG_HELPERS[parsed.language]
    lines: list[str] = [f"# file: {file_path}"]
    lines.extend(
        _render_body_lines(root, definition_ids, language_helpers, parsed, exclude_ids=import_ids)
    )

    code = "\n".join(lines)

    all_refs = extract_reference_records(root, parsed.content, parsed.ref_query)
    references = _filter_out_nested_refs(root, definition_ids, all_refs)

    return CodeChunk(
        chunk_id=stable_chunk_id(file_path, 0, f"<file_skeleton:{file_path}>"),
        full_name=file_path,
        name=file_path.rsplit("/", 1)[-1],
        defined_in_class=None,
        file_path=file_path,
        start_byte=0,
        end_byte=0,
        start_line=root.start_point[0] + 1,
        end_line=root.end_point[0] + 1,
        language=parsed.language,
        code=code,
        node_type=None,
        kind=ChunkKind.FILE_SKELETON,
        size_chars=len(code),
        references=references,
        parent_chunk_id=None,
    )
