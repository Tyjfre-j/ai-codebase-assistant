"""Language-agnostic AST and chunk-assembly helpers, shared by every language module."""

import hashlib
from dataclasses import replace

from tree_sitter import Node

from app.ingestion.chunk_model import ChunkType, CodeChunk


def node_text(node, content: bytes) -> str:
    """Extract the source text a node spans, from the original file bytes."""
    return content[node.start_byte:node.end_byte].decode("utf-8")


def node_lines(node) -> tuple[int, int]:
    """Return (start_line, end_line), 1-indexed."""
    return node.start_point[0] + 1, node.end_point[0] + 1


def make_chunk_id(file_path: str, qualified_name: str, source_code: str) -> str:
    """Content-based id: collision-resistant and memory-efficient."""
    h = hashlib.sha256() 
    h.update(file_path.encode("utf-8"))
    h.update(qualified_name.encode("utf-8"))
    h.update(source_code.encode("utf-8"))
    return h.hexdigest()[:16]


def find_enclosing_type(node, content: bytes, class_node_types: set[str]) -> str | None:
    """Walk up from a node to find an enclosing class/type node's name, if any."""
    current = node.parent
    while current is not None:
        if current.type in class_node_types:
            name_node = current.child_by_field_name("name")
            return node_text(name_node, content) if name_node is not None else None
        current = current.parent
    return None


def extract_param_names(params_node, content: bytes) -> tuple[str, ...]:
    """Pull each parameter's text from a parameter-list node's named children."""
    if params_node is None:
        return ()
    return tuple(node_text(child, content) for child in params_node.named_children)


def resolve_bound_name(module: str, bound_name: str | None, alias: str | None) -> str:
    """The identifier this import actually binds into local scope."""
    if alias is not None:
        return alias
    if bound_name is not None:
        return bound_name
    return module.rsplit(".", 1)[-1].rsplit("/", 1)[-1]


def build_type_skeleton(def_node, content: bytes, class_node_types: set[str], get_member_info) -> str:
    """Signature + attributes + one-line method stubs. Method BODIES live in their own chunks."""
    body_node = def_node.child_by_field_name("body")
    header_end = body_node.start_byte if body_node else def_node.end_byte
    lines = [content[def_node.start_byte:header_end].decode("utf-8").rstrip()]

    for child in (body_node.named_children if body_node else []):
        info = get_member_info(child, content)
        if info is not None:
            lines += [f"    {d}" for d in info["decorators"]]
            lines.append(f"    {info['prefix']} {info['name']}{info['params']}: ...")
        else:
            lines.append("    " + node_text(child, content))

    return "\n".join(lines)


def group_matches_by_anchor(matches, anchor_key: str) -> dict[int, list[dict]]:
    """Group matches sharing the same anchor node (e.g. one import statement, multiple bound names)."""
    grouped: dict[int, list[dict]] = {}
    for _pattern_idx, captures in matches:
        if anchor_key not in captures:
            continue
        anchor_id = captures[anchor_key][0].id
        grouped.setdefault(anchor_id, []).append(captures)
    return grouped


def extract_module_docstring(root_node, content: bytes, docstring_node_type: str = "string") -> str | None:
    """The first top-level statement's string literal, if there is one (Python-style module docstring)."""
    children = root_node.named_children
    if not children:
        return None
    first = children[0]
    if first.type == "expression_statement" and first.named_children:
        expr = first.named_children[0]
        if expr.type == docstring_node_type:
            return node_text(expr, content)
    return None


def filter_trivial_nested_chunks(chunks: list[CodeChunk], min_lines: int = 6) -> list[CodeChunk]:
    """Drop small nested closures whose code is already duplicated inside their parent chunk."""
    other_chunks = [c for c in chunks if c.chunk_type not in (ChunkType.FUNCTION, ChunkType.METHOD)]
    func_like = sorted(
        (c for c in chunks if c.chunk_type in (ChunkType.FUNCTION, ChunkType.METHOD)),
        key=lambda c: (c.start_line, -c.end_line),
    )

    keep: list[CodeChunk] = []
    stack: list[CodeChunk] = []
    for c in func_like:
        while stack and stack[-1].end_line < c.start_line:
            stack.pop()
        has_enclosing = bool(stack)
        size = c.end_line - c.start_line + 1
        if not (has_enclosing and size < min_lines):
            keep.append(c)
        stack.append(c)

    return sorted(keep + other_chunks, key=lambda c: c.start_line)


def build_leftover_chunks(
    root_node, chunks: list[CodeChunk], content: bytes, file_path: str, language: str
) -> list[CodeChunk]:
    """Wrap top-level statements not covered by any real chunk into MODULE_LEVEL chunks."""
    covered = {(c.start_line, c.end_line) for c in chunks}
    leftover_chunks: list[CodeChunk] = []
    current_group: list[Node] = []

    def flush_group():
        if not current_group:
            return
        start_line, _ = node_lines(current_group[0])
        _, end_line = node_lines(current_group[-1])
        node_types = sorted({n.type for n in current_group})
        source = content[current_group[0].start_byte:current_group[-1].end_byte].decode("utf-8")
        qualified_name = f"module-level ({', '.join(node_types)})"

        leftover_chunks.append(CodeChunk(
            chunk_id=make_chunk_id(file_path, f"{qualified_name}:{start_line}", source),
            file_path=file_path,
            language=language,
            chunk_type=ChunkType.MODULE_LEVEL,
            qualified_name=qualified_name,
            parameters=(),
            parent_class=None,
            imports=(),
            source_code=source,
            start_line=start_line,
            end_line=end_line,
        ))

    for child in root_node.named_children:
        if node_lines(child) in covered:
            flush_group()
            current_group = []
        else:
            current_group.append(child)
    flush_group()

    return leftover_chunks


def build_file_summary_chunk(
    module_docstring: str | None,
    imports: tuple[str, ...],
    top_level_symbols: list[str],
    content: bytes,
    file_path: str,
    language: str,
) -> CodeChunk:
    """One chunk per file, answering "what does this file do"."""
    lines = [f"File: {file_path}"]
    if module_docstring:
        lines.append(module_docstring.strip())
    if imports:
        lines.append("Imports: " + ", ".join(imports))
    if top_level_symbols:
        lines.append("Defines: " + ", ".join(top_level_symbols))
    text = "\n".join(lines)
    total_lines = content.count(b"\n") + 1

    return CodeChunk(
        chunk_id=make_chunk_id(file_path, "__file_summary__", text),
        file_path=file_path,
        language=language,
        chunk_type=ChunkType.FILE_SUMMARY,
        qualified_name=file_path,
        parameters=(),
        parent_class=None,
        imports=imports,
        source_code=text,
        start_line=1,
        end_line=total_lines,
    )


def build_embedding_text(chunk: CodeChunk) -> str:
    """What actually gets sent to the embedding model — a bit of header context, not just raw source."""
    header = f"# file: {chunk.file_path}\n"
    if chunk.imports:
        header += f"# imports: {', '.join(chunk.imports)}\n"
    if chunk.parent_class:
        header += f"# class: {chunk.parent_class}\n"
    return header + chunk.source_code


def approx_token_count(text: str) -> int:
    """Rough ~4 chars/token estimate — closer to a real tokenizer than word-splitting for code."""
    return max(1, len(text) // 4)


def _group_text(nodes: list, content: bytes) -> str:
    return content[nodes[0].start_byte:nodes[-1].end_byte].decode("utf-8")


def _greedy_group_children(children: list, content: bytes, max_tokens: int) -> list[list]:
    """Merge adjacent statements into token-budget-respecting groups (split-then-merge, cAST-style)."""
    groups = [], list[Node] = []
    for child in children:
        candidate = current + [child]
        if current and approx_token_count(_group_text(candidate, content)) > max_tokens:
            groups.append(current)
            current = [child]
        else:
            current = candidate
    if current:
        groups.append(current)
    return groups


def _split_by_token_window(chunk: CodeChunk, max_tokens: int, overlap_tokens: int = 50) -> list[CodeChunk]:
    """Last-resort raw character-window split, with overlap, for leaves with no smaller structure to cut."""
    text = chunk.source_code
    window, overlap = max_tokens * 4, overlap_tokens * 4
    parts, start, i = [], 0, 1
    while start < len(text):
        end = min(start + window, len(text))
        piece = text[start:end]
        parts.append(replace(
            chunk,
            chunk_id=make_chunk_id(chunk.file_path, f"{chunk.qualified_name}#window{i}", piece),
            qualified_name=f"{chunk.qualified_name}#window{i}",
            source_code=piece,
        ))
        if end == len(text):
            break
        start, i = end - overlap, i + 1
    return parts


def split_oversized_chunk(chunk: CodeChunk, parser, max_tokens: int, _depth: int = 0) -> list[CodeChunk]:
    """Recursively split an oversized chunk along its own re-parsed statement boundaries."""
    if approx_token_count(chunk.source_code) <= max_tokens:
        return [chunk]

    content = chunk.source_code.encode()
    root = parser.parse(content).root_node
    children = list(root.named_children)

    header = ""
    if len(children) == 1 and children[0].type in (
        "function_definition", "class_definition", "function_declaration", "method_definition"
    ):
        wrapper = children[0]
        body = wrapper.child_by_field_name("body")
        if body is not None and body.named_children:
            header_end = body.start_byte
            header = content[wrapper.start_byte:header_end].decode("utf-8").rstrip() + "\n"
            children = list(body.named_children)

    if not children:
        return _split_by_token_window(chunk, max_tokens)

    groups = _greedy_group_children(children, content, max_tokens)
    result = []
    for i, group in enumerate(groups):
        group_text = header + _group_text(group, content)
        real_start = chunk.start_line + (group[0].start_point[0] + 1) - 1
        real_end = chunk.start_line + (group[-1].end_point[0] + 1) - 1

        part = replace(
            chunk,
            chunk_id=make_chunk_id(chunk.file_path, f"{chunk.qualified_name}#part{i + 1}", group_text),
            qualified_name=f"{chunk.qualified_name}#part{i + 1}",
            source_code=group_text,
            start_line=real_start,
            end_line=real_end,
        )

        if approx_token_count(group_text) > max_tokens:
            if _depth >= 3:
                result.extend(_split_by_token_window(part, max_tokens))
            else:
                result.extend(split_oversized_chunk(part, parser, max_tokens, _depth + 1))
        else:
            result.append(part)
    return result


def chunk_size_manager(chunks: list[CodeChunk], parser, max_tokens: int = 800) -> list[CodeChunk]:
    """Split oversized chunks; never silently drop one — a big function still belongs in the index."""
    result = []
    for chunk in chunks:
        if chunk.chunk_type == ChunkType.FILE_SUMMARY:
            result.append(chunk)
            continue
        result.extend(split_oversized_chunk(chunk, parser, max_tokens))
    return result