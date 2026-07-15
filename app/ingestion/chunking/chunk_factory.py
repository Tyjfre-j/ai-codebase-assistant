from tree_sitter import Node

from app.core.exceptions import ChunkExtractionError
from app.ingestion.code_chunk import CodeChunk
from app.ingestion.languages import LANG_HELPERS
from app.ingestion.refs.extractor import extract_reference_records
from app.ingestion.source_parser import ParsedFile
from app.ingestion.source_text import extract_definition_name, node_text, node_text_range, stable_chunk_id


def build_definition_chunk(
    node: Node,
    chunk_kind: str,
    file_path: str,
    parsed: ParsedFile,
    captures: dict[str, list[Node]],
) -> CodeChunk:
    """Build a CodeChunk for a captured definition node."""
    language_helpers = LANG_HELPERS[parsed.language]
    defined_in_class = language_helpers.get_enclosing_class_name(node, captures, parsed.content)
    name = extract_definition_name(node, parsed.content)
    full_name = f"{defined_in_class}.{name}" if defined_in_class else name
    code = node_text(node, parsed.content)

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
        kind=chunk_kind,
        merged_names=None,
        size_chars=len(code),
    )


def build_leftover_code_chunk(nodes: list[Node], file_path: str, parsed: ParsedFile) -> CodeChunk:
    """Build a CodeChunk for adjacent non-definition source nodes."""
    start, end = nodes[0].start_byte, nodes[-1].end_byte
    code = node_text_range(start, end, parsed.content)

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
        kind="leftover",
        merged_names=None,
        size_chars=len(code),
    )


def build_class_skeleton_chunk(
    class_node: Node,
    file_path: str,
    parsed: ParsedFile,
) -> CodeChunk:
    """Build a compact class chunk that lists member signatures."""
    class_name = node_text(class_node.child_by_field_name("name"), parsed.content)
    stub_lines = [f"class {class_name}:"]

    body = class_node.child_by_field_name("body")
    get_member_stub_info = getattr(LANG_HELPERS[parsed.language], "get_class_member_stub_info", None)

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
                f"@{decorator}\n    " for decorator in member_info["decorators"]
            )
            # `prefix` is "def"/"async def" for Python but only "async"/"" for JS/TS
            # (JS/TS methods have no keyword when not async), so only prepend a
            # trailing space when a prefix actually exists.
            prefix = member_info["prefix"]
            keyword = f"{prefix} " if prefix else ""
            stub_lines.append(
                f"    {decorators}{keyword}"
                f"{member_info['name']}{member_info['params']}: ..."
            )

    if len(stub_lines) == 1:
        stub_lines.append("    ...")

    code = "\n".join(stub_lines)
    references = [
        ref for ref in extract_reference_records(class_node, parsed.content, parsed.ref_query)
        if ref.kind == "inheritance"
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
        kind="class_skeleton",
        merged_names=None,
        size_chars=len(code),
        references=references,
    )