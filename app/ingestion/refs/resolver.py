from dataclasses import replace

from app.ingestion.code_chunk import (
    CodeChunk,
    ImportBinding,
    ImportKind,
    ParsedFileChunks,
    RefRecord,
    RefStatus,
)
from app.ingestion.languages import LANG_HELPERS
from app.ingestion.refs import symbol_index as symbol_index_mod

def resolve_reference(
    ref: RefRecord,
    origin_chunk: CodeChunk,
    symbol_index: symbol_index_mod.SymbolIndex,
    import_bindings: dict[str, ImportBinding],
    wildcard_import_modules: list[str],
    builtin_names: set[str],
    self_reference_names: set[str],
) -> RefRecord:
    text = ref.text
    file_path = origin_chunk.file_path

    if "." in text:
        parts = text.split(".")
        clean_parts = [p.split("(")[0].split("[")[0] for p in parts]
        prefix = clean_parts[0]

        if prefix in self_reference_names:
            class_name = origin_chunk.defined_in_class
            # If this chunk itself is the class, use its full_name
            if not class_name and origin_chunk.kind in ("definition", "definition_skeleton"):
                class_name = origin_chunk.full_name

            if class_name:
                for i in range(len(clean_parts), 0, -1):
                    qualified = ".".join([class_name] + clean_parts[1:i])
                    chunk_id = symbol_index.by_full_name.get((file_path, qualified))
                    if chunk_id:
                        return replace(ref, points_to=chunk_id, status=RefStatus.LOCAL)

        for i in range(len(clean_parts), 0, -1):
            local_qualified = ".".join(clean_parts[:i])
            chunk_id = symbol_index.by_full_name.get((file_path, local_qualified))
            if chunk_id:
                return replace(ref, points_to=chunk_id, status=RefStatus.LOCAL)

        binding = import_bindings.get(prefix)
        if binding:
            if binding.resolved_path is None:
                return replace(ref, points_to=None, status=RefStatus.EXTERNAL)

            remaining = clean_parts[1 + binding.extra_segments:]
            if binding.kind == ImportKind.MODULE:
                for i in range(len(remaining), 0, -1):
                    qualified = ".".join(remaining[:i])
                    chunk_id = symbol_index.by_full_name.get((binding.resolved_path, qualified))
                    if chunk_id:
                        return replace(ref, points_to=chunk_id, status=RefStatus.LOCAL)
            else:
                for i in range(len(remaining), -1, -1):
                    qualified = ".".join([binding.remote_name] + remaining[:i])
                    chunk_id = symbol_index.by_full_name.get((binding.resolved_path, qualified))
                    if chunk_id:
                        return replace(ref, points_to=chunk_id, status=RefStatus.LOCAL)

        return replace(ref, points_to=None, status=RefStatus.UNRESOLVED)

    clean_text = text.split("(")[0].split("[")[0]

    chunk_id = symbol_index.by_full_name.get((file_path, clean_text))
    if chunk_id:
        return replace(ref, points_to=chunk_id, status=RefStatus.LOCAL)

    candidates = symbol_index.by_simple_name.get((file_path, clean_text))
    if candidates:
        return replace(ref, points_to=candidates[0], status=RefStatus.LOCAL)

    binding = import_bindings.get(clean_text)
    if binding:
        if binding.resolved_path is None:
            return replace(ref, points_to=None, status=RefStatus.EXTERNAL)
        chunk_id = symbol_index.by_full_name.get((binding.resolved_path, binding.remote_name))
        if chunk_id:
            return replace(ref, points_to=chunk_id, status=RefStatus.LOCAL)

    for module_path in wildcard_import_modules:
        chunk_id = symbol_index.by_full_name.get((module_path, clean_text))
        if chunk_id:
            return replace(ref, points_to=chunk_id, status=RefStatus.LOCAL)

    if clean_text in builtin_names:
        return replace(ref, points_to=None, status=RefStatus.BUILTIN)

    return replace(ref, points_to=None, status=RefStatus.UNRESOLVED)


def resolve_all_references(parsed_files: list[ParsedFileChunks]) -> None:
    all_chunks = [c for pf in parsed_files for c in pf.chunks]
    idx = symbol_index_mod.build_symbol_index(all_chunks)

    import_bindings_by_file = {pf.file_path: pf.import_bindings for pf in parsed_files}
    wildcard_modules_by_file = {pf.file_path: pf.wildcard_import_modules for pf in parsed_files}

    builtins_by_lang: dict[str, set[str]] = {}
    self_refs_by_lang: dict[str, set[str]] = {}
    for lang_name, lang_module in LANG_HELPERS.items():
        builtins_by_lang[lang_name] = getattr(lang_module, 'BUILTINS', set())
        self_refs_by_lang[lang_name] = getattr(lang_module, 'SELF_REFERENCE_NAMES', set())

    for pf in parsed_files:
        for i, chunk in enumerate(pf.chunks):
            file_bindings = import_bindings_by_file.get(chunk.file_path, {})
            file_wildcards = wildcard_modules_by_file.get(chunk.file_path, [])
            lang_builtins = builtins_by_lang.get(chunk.language, set())
            lang_self_refs = self_refs_by_lang.get(chunk.language, set())
            resolved_refs = [
                resolve_reference(
                    ref, chunk, idx, file_bindings, file_wildcards,
                    lang_builtins, lang_self_refs,
                )
                for ref in chunk.references
            ]
            pf.chunks[i] = replace(chunk, references=resolved_refs)