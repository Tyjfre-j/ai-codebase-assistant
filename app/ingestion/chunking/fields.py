import uuid

from tree_sitter import Node

from app.ingestion.chunk_builder_helpers import (
    extract_symbol_name,
    node_text,
    node_text_range,
)
from app.ingestion.chunk_model import CodeChunk
from app.ingestion.languages import LANG_HELPERS
from app.ingestion.parser import ParsedFile


def build_chunk(
    node: Node,
    chunk_kind: str,
    file_path: str,
    parsed: ParsedFile,
    captures: dict[str, list[Node]],
) -> CodeChunk:
    helpers = LANG_HELPERS[parsed.language]
    parent_symbol = helpers.resolve_parent_class(node, captures, parsed.content)
    symbol_name = extract_symbol_name(node, parsed.content)
    qualified_name = f"{parent_symbol}.{symbol_name}" if parent_symbol else symbol_name
    text = node_text(node, parsed.content)

    return CodeChunk(
        chunk_id=uuid.uuid4().hex,
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
    start, end = nodes[0].start_byte, nodes[-1].end_byte
    text = node_text_range(start, end, parsed.content)

    return CodeChunk(
        chunk_id=uuid.uuid4().hex,
        qualified_name=f"{file_path}:leftover:{start}",
        symbol_name="<leftover>",
        parent_symbol=None,
        file_path=file_path,
        start_byte=start,
        end_byte=end,
        language=parsed.language,
        content=text,
        docstring=None,
        node_type="leftover_group",
        chunk_kind="leftover",
        merged_symbols=None,
        size_chars=len(text),
    )

def build_class_skeleton_chunk(class_node, file_path: str, parsed: ParsedFile) -> CodeChunk:
    class_name = extract_symbol_name(class_node, parsed.content)
    stub_lines = [f"class {class_name}:"]

    body = class_node.child_by_field_name("body")
    get_member_info = getattr(LANG_HELPERS[parsed.language], "get_member_info", None)

    if body is not None and get_member_info is not None:
        for child in body.children:
            info = get_member_info(child, parsed.content)
            if info is None:
                continue
            decos = "".join(f"@{d}\n    " for d in info["decorators"])
            stub_lines.append(f"    {decos}{info['prefix']} {info['name']}{info['params']}: ...")
    else:
        stub_lines.append("    ...")  # language doesn't support member stubs yet

    text = "\n".join(stub_lines)
    return CodeChunk(
        chunk_id=uuid.uuid4().hex,
        qualified_name=class_name,
        symbol_name=class_name,
        parent_symbol=None,
        file_path=file_path,
        start_byte=class_node.start_byte,
        end_byte=class_node.start_byte,  # zero-width: synthetic content, not a real span
        language=parsed.language,
        content=text,
        docstring=None,
        node_type="class_skeleton",
        chunk_kind="class_skeleton",
        merged_symbols=None,
        size_chars=len(text),
    )