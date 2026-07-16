from collections import deque

from app.ingestion.code_chunk import ChunkKind, CodeChunk, ImportKind, ParsedFileChunks, RefKind, RefStatus


def _add_to_index(index: dict[str, list[str]], name: str, chunk_id: str) -> None:
    bucket = index.setdefault(name, [])
    if chunk_id not in bucket:
        bucket.append(chunk_id)

RESOLVABLE_KINDS = (ChunkKind.DEFINITION, ChunkKind.CLASS_SKELETON)

def build_definition_index(chunks: list[CodeChunk]) -> dict[str, list[str]]:
    """Aggregate definition/class-chunk names into a name -> chunk_id(s) index."""
    index: dict[str, list[str]] = {}
    for chunk in chunks:
        if chunk.kind not in RESOLVABLE_KINDS:
            continue
        _add_to_index(index, chunk.name, chunk.chunk_id)
        _add_to_index(index, chunk.full_name, chunk.chunk_id)
    return index


def build_file_symbol_index(chunks: list[CodeChunk]) -> dict[str, dict[str, list[str]]]:
    """Aggregate resolvable chunks per-file: file_path -> name -> chunk_id(s).

    Backs both same-file and import-target lookups, replacing what used to be a
    linear `[c for c in all_chunks if c.file_path == ... ]` scan per reference.
    """
    index: dict[str, dict[str, list[str]]] = {}
    for chunk in chunks:
        if chunk.kind not in RESOLVABLE_KINDS:
            continue
        file_index = index.setdefault(chunk.file_path, {})
        _add_to_index(file_index, chunk.name, chunk.chunk_id)
        _add_to_index(file_index, chunk.full_name, chunk.chunk_id)
    return index


def build_inheritance_graph(
    all_chunks: list[CodeChunk],
    chunk_by_id: dict[str, CodeChunk],
) -> dict[str, list[str]]:
    """Build class_name -> [parent_class_name, ...] from resolved inheritance refs.

    Uses the already-extracted INHERITANCE references on CLASS_SKELETON chunks.
    Each resolved ref's ``points_to`` is a chunk_id; we look that up to recover
    the parent class name and build the graph.
    """
    graph: dict[str, list[str]] = {}
    for chunk in all_chunks:
        if chunk.kind != ChunkKind.CLASS_SKELETON:
            continue
        parents: list[str] = []
        for ref in chunk.references:
            if ref.kind == RefKind.INHERITANCE and ref.points_to is not None:
                parent_chunk = chunk_by_id.get(ref.points_to)
                if parent_chunk is not None:
                    parents.append(parent_chunk.name)
        if parents:
            graph[chunk.name] = parents
    return graph


def _resolve_self_reference(
    text: str,
    chunk: CodeChunk,
    symbol_index: dict[str, list[str]],
    inheritance_graph: dict[str, list[str]],
) -> str | None:
    """Resolve self./cls./this. references, walking the inheritance chain if needed.

    For ``self.foo()`` in class ``Child``, this first checks ``Child.foo``.
    If not found and ``Child`` inherits from ``Base``, it checks ``Base.foo``,
    and so on up the MRO-like chain (BFS, with cycle protection).
    """
    for prefix in ("self.", "cls.", "this."):
        if text.startswith(prefix) and chunk.defined_in_class:
            rest = text[len(prefix):]

            # Try current class first.
            candidates = symbol_index.get(f"{chunk.defined_in_class}.{rest}", [])
            if len(candidates) == 1:
                return candidates[0]

            # Walk the inheritance chain (BFS).
            visited: set[str] = {chunk.defined_in_class}
            queue: deque[str] = deque(inheritance_graph.get(chunk.defined_in_class, []))
            while queue:
                parent_class = queue.popleft()
                if parent_class in visited:
                    continue
                visited.add(parent_class)
                candidates = symbol_index.get(f"{parent_class}.{rest}", [])
                if len(candidates) == 1:
                    return candidates[0]
                queue.extend(inheritance_graph.get(parent_class, []))

    return None


def _resolve_import_reference(
    text: str,
    import_bindings: dict[str, tuple[str | None, str, str]],
    file_symbol_index: dict[str, dict[str, list[str]]],
) -> str | None:
    root, _, rest = text.partition(".")
    binding = import_bindings.get(root)
    if binding is None:
        return None

    resolved_path, bound_name, import_kind = binding
    if resolved_path is None:
        return None

    if import_kind == ImportKind.MODULE:
        # `root` is the module itself; the actual symbol being referenced is
        # whatever follows it, e.g. `os.path.join` -> "path.join" inside "os".
        target_name = rest if rest else bound_name
    else:
        # `root` already IS the specific imported symbol (a "from X import Y"
        # binding); anything after "." is an attribute/method access on it,
        # not a separate top-level chunk to look up.
        target_name = bound_name

    candidates = file_symbol_index.get(resolved_path, {}).get(target_name, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def _resolve_same_file_reference(
    text: str, chunk: CodeChunk, file_symbol_index: dict[str, dict[str, list[str]]]
) -> str | None:
    candidates = file_symbol_index.get(chunk.file_path, {}).get(text, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def _resolve_global_reference(text: str, symbol_index: dict[str, list[str]]) -> str | None:
    candidates = symbol_index.get(text, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def resolve_chunk_references(
    chunk: CodeChunk,
    symbol_index: dict[str, list[str]],
    import_bindings: dict[str, tuple[str | None, str, str]],
    file_symbol_index: dict[str, dict[str, list[str]]],
    chunk_by_id: dict[str, CodeChunk],
    inheritance_graph: dict[str, list[str]],
) -> None:
    """Mutate chunk.references in place: self/cls -> import bindings -> same-file -> global fallback."""
    for ref in chunk.references:
        points_to = _resolve_self_reference(ref.text, chunk, symbol_index, inheritance_graph)
        if points_to is None:
            points_to = _resolve_import_reference(ref.text, import_bindings, file_symbol_index)
        if points_to is None:
            points_to = _resolve_same_file_reference(ref.text, chunk, file_symbol_index)
        if points_to is None:
            points_to = _resolve_global_reference(ref.text, symbol_index)

        if points_to is not None:
            target_chunk = chunk_by_id.get(points_to)
            if target_chunk is not None and target_chunk.language != chunk.language:
                points_to = None

        ref.points_to = points_to
        ref.status = RefStatus.LOCAL if points_to is not None else RefStatus.UNRESOLVED


def resolve_all_chunk_references(all_parsed_chunks: list[ParsedFileChunks]) -> None:
    """Mutate every chunk's references in place, resolving points_to and status across the whole repository."""
    all_chunks = [chunk for pc in all_parsed_chunks for chunk in pc.chunks]
    chunk_by_id = {chunk.chunk_id: chunk for chunk in all_chunks}
    symbol_index = build_definition_index(all_chunks)
    file_symbol_index = build_file_symbol_index(all_chunks)
    inheritance_graph = build_inheritance_graph(all_chunks, chunk_by_id)

    for parsed_chunks in all_parsed_chunks:
        for chunk in parsed_chunks.chunks:
            if chunk.kind not in (ChunkKind.DEFINITION, ChunkKind.CLASS_SKELETON):
                continue
            resolve_chunk_references(
                chunk, symbol_index, parsed_chunks.import_bindings,
                file_symbol_index, chunk_by_id, inheritance_graph,
            )