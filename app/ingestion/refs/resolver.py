import os
from collections import deque

from app.ingestion.code_chunk import ChunkKind, CodeChunk, ImportKind, ParsedFileChunks, RefKind, RefStatus


def _add_to_index(index: dict[str, list[str]], name: str, chunk_id: str) -> None:
    bucket = index.setdefault(name, [])
    if chunk_id not in bucket:
        bucket.append(chunk_id)

RESOLVABLE_KINDS = (ChunkKind.DEFINITION, ChunkKind.MERGED_GROUP, ChunkKind.CLASS_SKELETON, ChunkKind.FUNCTION_SKELETON)

def build_definition_index(chunks: list[CodeChunk]) -> dict[str, list[str]]:
    """Aggregate definition/class/function-chunk names into a name -> chunk_id(s) index."""
    index: dict[str, list[str]] = {}
    for chunk in chunks:
        if chunk.kind not in RESOLVABLE_KINDS:
            continue
        _add_to_index(index, chunk.name, chunk.chunk_id)
        _add_to_index(index, chunk.full_name, chunk.chunk_id)
    return index


def build_file_symbol_index(chunks: list[CodeChunk]) -> dict[str, dict[str, list[str]]]:
    """Aggregate resolvable chunks per-file: file_path -> name -> chunk_id(s)."""
    index: dict[str, dict[str, list[str]]] = {}
    for chunk in chunks:
        if chunk.kind not in RESOLVABLE_KINDS:
            continue
        file_index = index.setdefault(chunk.file_path, {})
        _add_to_index(file_index, chunk.name, chunk.chunk_id)
        _add_to_index(file_index, chunk.full_name, chunk.chunk_id)
    return index


def build_dir_symbol_index(chunks: list[CodeChunk]) -> dict[str, dict[str, list[str]]]:
    """Aggregate resolvable chunks per-directory: dir_path -> name -> chunk_id(s)."""
    index: dict[str, dict[str, list[str]]] = {}
    for chunk in chunks:
        if chunk.kind not in RESOLVABLE_KINDS:
            continue
        dir_path = os.path.dirname(chunk.file_path)
        dir_index = index.setdefault(dir_path, {})
        _add_to_index(dir_index, chunk.name, chunk.chunk_id)
        _add_to_index(dir_index, chunk.full_name, chunk.chunk_id)
    return index


def build_inheritance_graph(
    all_chunks: list[CodeChunk],
    chunk_by_id: dict[str, CodeChunk],
) -> dict[str, list[str]]:
    """Build class_chunk_id -> [parent_chunk_id, ...] from resolved inheritance refs."""
    graph: dict[str, list[str]] = {}
    for chunk in all_chunks:
        if chunk.kind != ChunkKind.CLASS_SKELETON:
            continue
        parents: list[str] = []
        for ref in chunk.references:
            if ref.kind == RefKind.INHERITANCE and ref.points_to is not None:
                # Only include parents that actually exist in the chunk index
                if ref.points_to in chunk_by_id:
                    parents.append(ref.points_to)
        if parents:
            graph[chunk.chunk_id] = parents
    return graph

def _resolve_self_reference(
    text: str,
    chunk: CodeChunk,
    symbol_index: dict[str, list[str]],
    inheritance_graph: dict[str, list[str]],
    file_symbol_index: dict[str, dict[str, list[str]]],
    chunk_by_id: dict[str, CodeChunk],
) -> str | None:
    """Resolve self./cls./this. references, walking the inheritance chain if needed."""
    for prefix in ("self.", "cls.", "this."):
        if text.startswith(prefix) and chunk.defined_in_class:
            rest = text[len(prefix):]

            candidates = file_symbol_index.get(chunk.file_path, {}).get(f"{chunk.defined_in_class}.{rest}", [])
            if len(candidates) != 1:
                candidates = symbol_index.get(f"{chunk.defined_in_class}.{rest}", [])
            if len(candidates) == 1:
                return candidates[0]

            class_candidates = file_symbol_index.get(chunk.file_path, {}).get(chunk.defined_in_class, [])
            if len(class_candidates) != 1:
                continue
            class_chunk_id = class_candidates[0]

            visited: set[str] = {class_chunk_id}
            queue: deque[str] = deque(inheritance_graph.get(class_chunk_id, []))
            while queue:
                parent_chunk_id = queue.popleft()
                if parent_chunk_id in visited:
                    continue
                visited.add(parent_chunk_id)
                
                parent_chunk = chunk_by_id.get(parent_chunk_id)
                if parent_chunk is None:
                    continue

                candidates = file_symbol_index.get(parent_chunk.file_path, {}).get(f"{parent_chunk.name}.{rest}", [])
                if len(candidates) == 1:
                    return candidates[0]
                queue.extend(inheritance_graph.get(parent_chunk_id, []))

    return None


def _resolve_import_reference(
    text: str,
    import_bindings: dict[str, tuple[str | None, str, str]],
    file_symbol_index: dict[str, dict[str, list[str]]],
    dir_symbol_index: dict[str, dict[str, list[str]]],
) -> str | None:
    root, _, rest = text.partition(".")
    binding = import_bindings.get(root)
    if binding is None:
        return None

    resolved_path, bound_name, import_kind = binding
    if resolved_path is None:
        return None

    if import_kind == ImportKind.MODULE:
        target_name = rest if rest else bound_name
    else:
        target_name = bound_name

    candidates = file_symbol_index.get(resolved_path, {}).get(target_name, [])
    if not candidates:
        candidates = dir_symbol_index.get(resolved_path, {}).get(target_name, [])
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


def _is_external_import(
    text: str,
    import_bindings: dict[str, tuple[str | None, str, str]],
) -> bool:
    root, _, _ = text.partition(".")
    binding = import_bindings.get(root)
    if binding is not None:
        resolved_path, _, _ = binding
        return resolved_path is None
    return False


def resolve_chunk_references(
    chunk: CodeChunk,
    symbol_index: dict[str, list[str]],
    import_bindings: dict[str, tuple[str | None, str, str]],
    file_symbol_index: dict[str, dict[str, list[str]]],
    dir_symbol_index: dict[str, dict[str, list[str]]],
    chunk_by_id: dict[str, CodeChunk],
    inheritance_graph: dict[str, list[str]],
) -> None:
    """Mutate chunk.references in place: self/cls -> same-file -> import -> global fallback."""
    from app.ingestion.languages import LANG_HELPERS
    language_helpers = LANG_HELPERS.get(chunk.language)
    is_builtin = getattr(language_helpers, "is_builtin", lambda name: False) if language_helpers else lambda name: False

    for ref in chunk.references:
        # 1. self./cls./this. references (most specific)
        points_to = _resolve_self_reference(
            ref.text, chunk, symbol_index, inheritance_graph, file_symbol_index, chunk_by_id
        )
        
        # 2. Same-file definitions (local shadows import)
        if points_to is None:
            points_to = _resolve_same_file_reference(ref.text, chunk, file_symbol_index)
        
        # 3. Import bindings
        if points_to is None:
            points_to = _resolve_import_reference(
                ref.text, import_bindings, file_symbol_index, dir_symbol_index
            )
        
        # 4. Global fallback (any file in repo)
        if points_to is None:
            points_to = _resolve_global_reference(ref.text, symbol_index)

        # Language boundary check
        if points_to is not None:
            target_chunk = chunk_by_id.get(points_to)
            if target_chunk is not None and target_chunk.language != chunk.language:
                points_to = None

        ref.points_to = points_to
        if points_to is not None:
            ref.status = RefStatus.LOCAL
        else:
            root, _, _ = ref.text.partition(".")
            if _is_external_import(ref.text, import_bindings):
                ref.status = RefStatus.EXTERNAL
            elif is_builtin(root):
                ref.status = RefStatus.BUILTIN
            else:
                ref.status = RefStatus.UNRESOLVED


def resolve_all_chunk_references(all_parsed_chunks: list[ParsedFileChunks]) -> None:
    """Mutate every chunk's references in place, resolving points_to and status across the whole repository."""
    all_chunks = [chunk for pc in all_parsed_chunks for chunk in pc.chunks]
    chunk_by_id = {chunk.chunk_id: chunk for chunk in all_chunks}
    symbol_index = build_definition_index(all_chunks)
    file_symbol_index = build_file_symbol_index(all_chunks)
    dir_symbol_index = build_dir_symbol_index(all_chunks)
    inheritance_graph = build_inheritance_graph(all_chunks, chunk_by_id)

    for parsed_chunks in all_parsed_chunks:
        for chunk in parsed_chunks.chunks:
            if chunk.kind not in RESOLVABLE_KINDS:
                continue
            resolve_chunk_references(
                chunk, symbol_index, parsed_chunks.import_bindings,
                file_symbol_index, dir_symbol_index, chunk_by_id, inheritance_graph,
            )