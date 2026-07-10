from tree_sitter import Node

from app.core.exceptions import ChunkExtractionError
from app.ingestion.code_chunk import CodeChunk
from app.ingestion.languages import LANG_HELPERS
from app.ingestion.source_parser import ParsedFile
from app.ingestion.source_text import (
    extract_symbol_name,
    node_text,
    node_text_range,
    stable_chunk_id,
)


def build_chunk(
    node: Node,
    chunk_kind: str,
    file_path: str,
    parsed: ParsedFile,
    captures: dict[str, list[Node]],
) -> CodeChunk:
    """Build a CodeChunk for a captured definition node."""
    language_helpers = LANG_HELPERS[parsed.language]
    parent_symbol = language_helpers.resolve_parent_class(node, captures, parsed.content)
    symbol_name = extract_symbol_name(node, parsed.content)
    qualified_name = f"{parent_symbol}.{symbol_name}" if parent_symbol else symbol_name
    text = node_text(node, parsed.content)

    return CodeChunk(
        chunk_id=stable_chunk_id(file_path, node.start_byte, qualified_name),
        qualified_name=qualified_name,
        symbol_name=symbol_name,
        parent_symbol=parent_symbol,
        file_path=file_path,
        start_byte=node.start_byte,
        end_byte=node.end_byte,
        language=parsed.language,
        content=text,
        docstring=None,
        node_type=node.type,
        chunk_kind=chunk_kind,
        merged_symbols=None,
        size_chars=len(text),
    )


def build_leftover_chunk(nodes: list[Node], file_path: str, parsed: ParsedFile) -> CodeChunk:
    """Build a CodeChunk for adjacent non-definition source nodes."""
    start, end = nodes[0].start_byte, nodes[-1].end_byte
    text = node_text_range(start, end, parsed.content)

    return CodeChunk(
        chunk_id=stable_chunk_id(file_path, start, f"<leftover:{start}>"),
        qualified_name=f"{file_path}:leftover:{start}",
        symbol_name="<leftover>",
        parent_symbol=None,
        file_path=file_path,
        start_byte=start,
        end_byte=end,
        language=parsed.language,
        content=text,
        docstring=None,
        node_type=None,
        chunk_kind="leftover",
        merged_symbols=None,
        size_chars=len(text),
    )

def build_class_skeleton_chunk(
    class_node: Node,
    file_path: str,
    parsed: ParsedFile,
) -> CodeChunk:
    """Build a compact class chunk that lists member signatures."""
    class_name = extract_symbol_name(class_node, parsed.content)
    stub_lines = [f"class {class_name}:"]

    body = class_node.child_by_field_name("body")
    get_member_info = getattr(LANG_HELPERS[parsed.language], "get_member_info", None)

    if body is not None and get_member_info is not None:
        for child in body.children:
            try:
                member_info = get_member_info(child, parsed.content)
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
            stub_lines.append(
                f"    {decorators}{member_info['prefix']} "
                f"{member_info['name']}{member_info['params']}: ..."
            )

    if len(stub_lines) == 1:
        stub_lines.append("    ...")

    text = "\n".join(stub_lines)
    return CodeChunk(
        chunk_id=stable_chunk_id(file_path, class_node.start_byte, class_name),
        qualified_name=class_name,
        symbol_name=class_name,
        parent_symbol=None,
        file_path=file_path,
        start_byte=class_node.start_byte,
        end_byte=class_node.start_byte,
        language=parsed.language,
        content=text,
        docstring=None,
        node_type=None,
        chunk_kind="class_skeleton",
        merged_symbols=None,
        size_chars=len(text),
    )