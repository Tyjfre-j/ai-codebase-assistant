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
    parent_chunk_id: str | None = None,
) -> CodeChunk:
    """Build a CodeChunk for a captured definition node."""
    language_helpers = LANG_HELPERS[parsed.language]
    defined_in_class = language_helpers.get_enclosing_class_name(node, captures, parsed.content)
    name = language_helpers.get_definition_name(node, parsed.content)

    get_namespace = getattr(language_helpers, "get_namespace", None)
    namespace = get_namespace(node, captures, parsed.content) if get_namespace else []

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
        parent_chunk_id=parent_chunk_id,
    )


def build_leftover_code_chunk(
    segments: list[list[Node]],
    file_path: str,
    parsed: ParsedFile,
    parent_chunk_id: str | None = None,
) -> CodeChunk:
    """Build a CodeChunk from one or more contiguous non-definition node segments."""
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
        parent_chunk_id=parent_chunk_id,
    )


def build_file_overview_chunk(
    root: Node,
    file_path: str,
    parsed: ParsedFile,
    top_level_names: list[str],
    import_text: str,
) -> CodeChunk:
    """Build a lightweight per-file chunk listing imports and top-level definition names."""
    language_helpers = LANG_HELPERS[parsed.language]
    get_module_docstring = getattr(language_helpers, "get_module_docstring", None)
    docstring = get_module_docstring(root, parsed.content) if get_module_docstring else None

    lines = [f"# file: {file_path}"]
    if docstring:
        lines.append(docstring.strip())
    if import_text:
        lines.append("# imports:")
        lines.append(import_text)
    if top_level_names:
        lines.append("# defines:")
        lines.extend(f"#   {name}" for name in top_level_names)

    code = "\n".join(lines)

    return CodeChunk(
        chunk_id=stable_chunk_id(file_path, 0, "<file_overview>"),
        full_name=f"{file_path}:overview",
        name="<file_overview>",
        defined_in_class=None,
        file_path=file_path,
        start_byte=0,
        end_byte=0,
        language=parsed.language,
        code=code,
        docstring=None,
        node_type=None,
        kind=ChunkKind.FILE_OVERVIEW,
        merged_names=None,
        size_chars=len(code),
        parent_chunk_id=None,
    )


def build_class_skeleton_chunk(
    class_node: Node,
    file_path: str,
    parsed: ParsedFile,
    captures: dict[str, list[Node]],
    parent_chunk_id: str | None = None,
) -> CodeChunk:
    """Build a compact class chunk that lists all class-level code and member signatures."""
    name_node = class_node.child_by_field_name("name")
    class_name = node_text(name_node, parsed.content) if name_node is not None else "<unknown>"
    language_helpers = LANG_HELPERS[parsed.language]

    get_namespace = getattr(language_helpers, "get_namespace", None)
    namespace = get_namespace(class_node, captures, parsed.content) if get_namespace else []
    if namespace:
        full_name = ".".join(namespace + [class_name])
    else:
        full_name = class_name

    get_header = getattr(language_helpers, "get_class_skeleton_header", None)
    get_footer = getattr(language_helpers, "get_class_skeleton_footer", None)
    header = get_header(class_name) if get_header else f"class {class_name}:"
    footer = get_footer() if get_footer else None

    body = class_node.child_by_field_name("body")
    get_member_stub_info = getattr(language_helpers, "get_class_member_stub_info", None)

    member_lines: list[str] = []
    if body is not None:
        for child in body.children:
            # Try to render as method stub first
            if get_member_stub_info is not None:
                try:
                    member_info = get_member_stub_info(child, parsed.content)
                except Exception as e:
                    raise ChunkExtractionError(
                        f"Failed extracting member info for {class_name} "
                        f"(node type={child.type}): {e}"
                    ) from e

                if member_info is not None:
                    decorators = "".join(
                        f"{decorator}\n    " for decorator in member_info["decorators"]
                    )
                    prefix = member_info["prefix"]
                    keyword = f"{prefix} " if prefix else ""
                    member_lines.append(
                        f"    {decorators}{keyword}"
                        f"{member_info['name']}{member_info['params']}: ..."
                    )
                    continue

            # Not a method — render as class-level code (docstring, variable, etc.)
            text = node_text(child, parsed.content).strip()
            if text:
                indented = "\n".join(
                    f"    {line}" if line.strip() else line
                    for line in text.split("\n")
                )
                member_lines.append(indented)

    if not member_lines:
        member_lines.append("    ...")

    stub_lines = [header, *member_lines]
    if footer is not None:
        stub_lines.append(footer)

    code = "\n".join(stub_lines)

    all_refs = extract_reference_records(class_node, parsed.content, parsed.ref_query)
    references = [ref for ref in all_refs if ref.kind == RefKind.INHERITANCE]

    return CodeChunk(
        chunk_id=stable_chunk_id(file_path, class_node.start_byte, full_name),
        full_name=full_name,
        name=class_name,
        defined_in_class=None,
        file_path=file_path,
        start_byte=class_node.start_byte,
        end_byte=class_node.start_byte,
        language=parsed.language,
        code=code,
        docstring=None,
        node_type=class_node.type,
        kind=ChunkKind.CLASS_SKELETON,
        merged_names=None,
        size_chars=len(code),
        references=references,
        parent_chunk_id=parent_chunk_id,
    )


def build_function_skeleton_chunk(
    func_node: Node,
    file_path: str,
    parsed: ParsedFile,
    captures: dict[str, list[Node]],
    parent_chunk_id: str | None = None,
) -> CodeChunk:
    """Build a compact function chunk that just lists its signature."""
    language_helpers = LANG_HELPERS[parsed.language]
    defined_in_class = language_helpers.get_enclosing_class_name(func_node, captures, parsed.content)
    name = language_helpers.get_definition_name(func_node, parsed.content)

    get_namespace = getattr(language_helpers, "get_namespace", None)
    namespace = get_namespace(func_node, captures, parsed.content) if get_namespace else []

    if namespace:
        full_name = ".".join(namespace + [name])
    elif defined_in_class:
        full_name = f"{defined_in_class}.{name}"
    else:
        full_name = name

    # Handle decorated_definition wrapper for body lookup
    body_node = func_node.child_by_field_name("body")
    if body_node is None and func_node.type == "decorated_definition":
        inner_def = func_node.child_by_field_name("definition")
        if inner_def is not None:
            body_node = inner_def.child_by_field_name("body")

    if body_node is not None:
        code = node_text_range(func_node.start_byte, body_node.start_byte, parsed.content) + "..."
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
        node_type=func_node.type,
        kind=ChunkKind.FUNCTION_SKELETON,
        merged_names=None,
        size_chars=len(code),
        references=[],
        parent_chunk_id=parent_chunk_id,
    )