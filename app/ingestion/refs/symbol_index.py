from dataclasses import dataclass, field

from app.ingestion.code_chunk import ChunkKind, CodeChunk


@dataclass
class SymbolIndex:
    by_full_name: dict[tuple[str, str], str] = field(default_factory=dict)
    by_simple_name: dict[tuple[str, str], list[str]] = field(default_factory=dict)


def build_symbol_index(all_chunks: list[CodeChunk]) -> SymbolIndex:
    index = SymbolIndex()

    for chunk in all_chunks:
        if chunk.kind not in (ChunkKind.DEFINITION, ChunkKind.DEFINITION_SKELETON):
            continue

        key = (chunk.file_path, chunk.full_name)
        if key not in index.by_full_name:
            index.by_full_name[key] = chunk.chunk_id

        simple_key = (chunk.file_path, chunk.name)
        index.by_simple_name.setdefault(simple_key, []).append(chunk.chunk_id)

        for folded_full_name in chunk.contained_symbols:
            folded_key = (chunk.file_path, folded_full_name)
            if folded_key not in index.by_full_name:
                index.by_full_name[folded_key] = chunk.chunk_id

    return index