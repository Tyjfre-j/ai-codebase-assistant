from tree_sitter import Node

from app.core.exceptions import ChunkExtractionError
from app.ingestion.code_chunk import ChunkKind, CodeChunk, RefKind
from app.ingestion.languages import LANG_HELPERS
from app.ingestion.refs.extractor import extract_reference_records
from app.ingestion.source_parser import ParsedFile
from app.ingestion.source_text import node_text, node_text_range, stable_chunk_id


def build_definition_chunk(
    node: Node,
    file_path: str,
    parsed: ParsedFile,
    captures: dict[str, list[Node]],
) -> CodeChunk:
    """Build a CodeChunk for a captured definition node."""
    language_helpers = LANG_HELPERS[parsed.language]
    defined_in_class = language_helpers.get_enclosing_class_name(node, captures, parsed.content)
    name = language_helpers.get_definition_name(node, parsed.content)
    
    get_namespace = getattr(language_helpers, "get_namespace", None)
    if get_namespace:
        namespace = get_namespace(node, captures, parsed.content)
    else:
        namespace = []

    if namespace:
        full_name = ".".join(namespace + [name])
    elif defined_in_class:
        full_name = f"{defined_in_class}.{name}"
    else:
        full_name = name
    code = node_text(node, parsed.content)
    references = extract_reference_records(node, parsed.content, parsed.ref_query)

    return CodeChunk(
        chunk_id=stable_chunk_id(file_path, node.start_byte, full_name),
        full_name=full_name,
        name=name,
        defined_in_class=defined_in_class,
        file_path=file_path,
        start_byte=node.start_byte,
        end_byte=node.end_byte,
        language=parsed.language,
        code=code,
        docstring=None,
        node_type=node.type,
        kind=ChunkKind.DEFINITION,
        merged_names=None,
        size_chars=len(code),
        references=references,
    )


def build_leftover_code_chunk(
    segments: list[list[Node]], file_path: str, parsed: ParsedFile
) -> CodeChunk:
    """Build a CodeChunk from one or more contiguous non-definition node segments.

    Each segment is a maximal run of nodes that were adjacent in the original
    source with nothing filtered out between them (the caller splits exactly at
    import boundaries to guarantee this). That makes it safe to slice each
    segment's own [start_byte, end_byte) range directly - preserving exact
    original formatting/whitespace within it - while segments are joined with a
    plain newline, since anything that originally sat *between* segments (e.g.
    an import statement) was deliberately excluded and must not reappear here.
    """
    start, end = segments[0][0].start_byte, segments[-1][-1].end_byte
    code = "\n".join(
        node_text_range(segment[0].start_byte, segment[-1].end_byte, parsed.content)
        for segment in segments
    )

    return CodeChunk(
        chunk_id=stable_chunk_id(file_path, start, f"<leftover:{start}>"),
        full_name=f"{file_path}:leftover:{start}",
        name="<leftover>",
        defined_in_class=None,
        file_path=file_path,
        start_byte=start,
        end_byte=end,
        language=parsed.language,
        code=code,
        docstring=None,
        node_type=None,
        kind=ChunkKind.LEFTOVER,
        merged_names=None,
        size_chars=len(code),
    )


def build_class_skeleton_chunk(
    class_node: Node,
    file_path: str,
    parsed: ParsedFile,
) -> CodeChunk:
    """Build a compact class chunk that lists member signatures."""
    name_node = class_node.child_by_field_name("name")
    class_name = node_text(name_node, parsed.content) if name_node is not None else "<unknown>"
    language_helpers = LANG_HELPERS[parsed.language]

    get_header = getattr(language_helpers, "get_class_skeleton_header", None)
    get_footer = getattr(language_helpers, "get_class_skeleton_footer", None)
    header = get_header(class_name) if get_header else f"class {class_name}:"
    footer = get_footer() if get_footer else None

    body = class_node.child_by_field_name("body")
    get_member_stub_info = getattr(language_helpers, "get_class_member_stub_info", None)

    member_lines: list[str] = []
    if body is not None and get_member_stub_info is not None:
        for child in body.children:
            try:
                member_info = get_member_stub_info(child, parsed.content)
            except Exception as e:
                raise ChunkExtractionError(
                    f"Failed extracting member info for {class_name} "
                    f"(node type={child.type}): {e}"
                ) from e

            if member_info is None:
                continue

            decorators = "".join(
                f"{decorator}\n    " for decorator in member_info["decorators"]
            )
            prefix = member_info["prefix"]
            keyword = f"{prefix} " if prefix else ""
            member_lines.append(
                f"    {decorators}{keyword}"
                f"{member_info['name']}{member_info['params']}: ..."
            )

    if not member_lines:
        member_lines.append("    ...")

    stub_lines = [header, *member_lines]
    if footer is not None:
        stub_lines.append(footer)

    code = "\n".join(stub_lines)
    references = [
        ref for ref in extract_reference_records(class_node, parsed.content, parsed.ref_query)
        if ref.kind == RefKind.INHERITANCE
    ]
    return CodeChunk(
        chunk_id=stable_chunk_id(file_path, class_node.start_byte, class_name),
        full_name=class_name,
        name=class_name,
        defined_in_class=None,
        file_path=file_path,
        start_byte=class_node.start_byte,
        end_byte=class_node.start_byte,
        language=parsed.language,
        code=code,
        docstring=None,
        node_type=None,
        kind=ChunkKind.CLASS_SKELETON,
        merged_names=None,
        size_chars=len(code),
        references=references,
    )


def build_function_skeleton_chunk(
    func_node: Node,
    file_path: str,
    parsed: ParsedFile,
    captures: dict[str, list[Node]],
) -> CodeChunk:
    """Build a compact function chunk that just lists its signature."""
    language_helpers = LANG_HELPERS[parsed.language]
    defined_in_class = language_helpers.get_enclosing_class_name(func_node, captures, parsed.content)
    name = language_helpers.get_definition_name(func_node, parsed.content)

    get_namespace = getattr(language_helpers, "get_namespace", None)
    if get_namespace:
        namespace = get_namespace(func_node, captures, parsed.content)
    else:
        namespace = []

    if namespace:
        full_name = ".".join(namespace + [name])
    elif defined_in_class:
        full_name = f"{defined_in_class}.{name}"
    else:
        full_name = name

    body = func_node.child_by_field_name("body")
    if body is not None:
        code = node_text_range(func_node.start_byte, body.start_byte, parsed.content) + "..."
    else:
        code = node_text(func_node, parsed.content)

    return CodeChunk(
        chunk_id=stable_chunk_id(file_path, func_node.start_byte, full_name),
        full_name=full_name,
        name=name,
        defined_in_class=defined_in_class,
        file_path=file_path,
        start_byte=func_node.start_byte,
        end_byte=func_node.start_byte,
        language=parsed.language,
        code=code,
        docstring=None,
        node_type=None,
        kind=ChunkKind.FUNCTION_SKELETON,
        merged_names=None,
        size_chars=len(code),
    )