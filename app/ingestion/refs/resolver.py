from app.ingestion.code_chunk import CodeChunk, ParsedFileChunks


def _add_to_index(index: dict[str, list[str]], name: str, chunk_id: str) -> None:
    bucket = index.setdefault(name, [])
    if chunk_id not in bucket:
        bucket.append(chunk_id)


def build_definition_index(chunks: list[CodeChunk]) -> dict[str, list[str]]:
    """Aggregate definition-chunk names into a name -> chunk_id(s) index."""
    index: dict[str, list[str]] = {}
    for chunk in chunks:
        if chunk.kind != "definition":
            continue
        _add_to_index(index, chunk.name, chunk.chunk_id)
        _add_to_index(index, chunk.full_name, chunk.chunk_id)
    return index


def _resolve_self_reference(text: str, chunk: CodeChunk, symbol_index: dict[str, list[str]]) -> str | None:
    for prefix in ("self.", "cls.", "this."):
        if text.startswith(prefix) and chunk.defined_in_class:
            rest = text[len(prefix):]
            candidates = symbol_index.get(f"{chunk.defined_in_class}.{rest}", [])
            if len(candidates) == 1:
                return candidates[0]
    return None


def _resolve_import_reference(
    text: str,
    import_bindings: dict[str, tuple[str | None, str]],
    all_chunks: list[CodeChunk],
) -> str | None:
    root, _, rest = text.partition(".")
    binding = import_bindings.get(root)
    if binding is None:
        return None

    resolved_path, bound_name = binding
    if resolved_path is None:
        return None

    target_name = f"{bound_name}.{rest}" if rest else bound_name

    candidates = [
        c for c in all_chunks
        if c.file_path == resolved_path and c.kind == "definition"
        and (c.name == target_name or c.full_name == target_name)
    ]
    if len(candidates) == 1:
        return candidates[0].chunk_id
    return None


def _resolve_same_file_reference(text: str, chunk: CodeChunk, all_chunks: list[CodeChunk]) -> str | None:
    candidates = [
        c for c in all_chunks
        if c.file_path == chunk.file_path and c.kind == "definition"
        and (c.name == text or c.full_name == text)
    ]
    if len(candidates) == 1:
        return candidates[0].chunk_id
    return None


def _resolve_global_reference(text: str, symbol_index: dict[str, list[str]]) -> str | None:
    candidates = symbol_index.get(text, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def resolve_chunk_references(
    chunk: CodeChunk,
    symbol_index: dict[str, list[str]],
    import_bindings: dict[str, tuple[str | None, str]],
    all_chunks: list[CodeChunk],
    chunk_by_id: dict[str, CodeChunk],
) -> None:
    """Mutate chunk.references in place: self/cls -> import bindings -> same-file -> global fallback."""
    for ref in chunk.references:
        points_to = _resolve_self_reference(ref.text, chunk, symbol_index)
        if points_to is None:
            points_to = _resolve_import_reference(ref.text, import_bindings, all_chunks)
        if points_to is None:
            points_to = _resolve_same_file_reference(ref.text, chunk, all_chunks)
        if points_to is None:
            points_to = _resolve_global_reference(ref.text, symbol_index)

        if points_to is not None:
            target_chunk = chunk_by_id.get(points_to)
            if target_chunk is not None and target_chunk.language != chunk.language:
                points_to = None

        ref.points_to = points_to
        ref.status = "local" if points_to is not None else "unresolved"


def resolve_all_chunk_references(all_parsed_chunks: list[ParsedFileChunks]) -> None:
    """Mutate every chunk's references in place, resolving points_to and status across the whole repository."""
    all_chunks = [chunk for pc in all_parsed_chunks for chunk in pc.chunks]
    chunk_by_id = {chunk.chunk_id: chunk for chunk in all_chunks}
    symbol_index = build_definition_index(all_chunks)

    for parsed_chunks in all_parsed_chunks:
        for chunk in parsed_chunks.chunks:
            if chunk.kind not in ("definition", "class_skeleton"):
                continue
            resolve_chunk_references(chunk, symbol_index, parsed_chunks.import_bindings, all_chunks, chunk_by_id)