from dataclasses import replace

from app.ingestion.code_chunk import ChunkKind, CodeChunk
from app.ingestion.source_text import stable_chunk_id

MERGEABLE_KINDS = {ChunkKind.DEFINITION, ChunkKind.MERGED_GROUP}


def merge_adjacent_defs(chunks: list[CodeChunk], budget: int) -> list[CodeChunk]:
    """Merge adjacent, same-scope definition chunks while respecting the size budget.
    
    Skeleton chunks pass through untouched. Only DEFINITION and MERGED_GROUP
    chunks are candidates. Chunks must share the same parent_chunk_id to merge.
    """
    merged: list[CodeChunk] = []
    buffer: CodeChunk | None = None

    for chunk in chunks:
        # Skeletons pass through untouched — never merged
        if chunk.kind in (ChunkKind.CLASS_SKELETON, ChunkKind.FUNCTION_SKELETON):
            if buffer is not None:
                merged.append(buffer)
                buffer = None
            merged.append(chunk)
            continue

        # Only mergeable kinds participate
        if chunk.kind not in MERGEABLE_KINDS:
            if buffer is not None:
                merged.append(buffer)
                buffer = None
            merged.append(chunk)
            continue

        if buffer is None:
            buffer = chunk
            continue

        # Same scope (same parent) and fits budget → merge
        same_scope = buffer.parent_chunk_id == chunk.parent_chunk_id
        fits_budget = (buffer.size_chars + chunk.size_chars) <= budget

        if same_scope and fits_budget:
            buffer = combine_chunks(buffer, chunk)
        else:
            merged.append(buffer)
            buffer = chunk

    if buffer is not None:
        merged.append(buffer)
    return merged


def combine_chunks(first: CodeChunk, second: CodeChunk) -> CodeChunk:
    """Return a single chunk with metadata from two adjacent, same-scope definitions."""
    merged_names = (
        first.merged_names or [first.name]
    ) + (
        second.merged_names or [second.name]
    )
    combined_name = f"{first.name}+{second.name}"
    combined_full_name = f"{first.full_name}+{second.full_name}"
    return replace(
        first,
        chunk_id=stable_chunk_id(first.file_path, first.start_byte, combined_full_name),
        end_byte=second.end_byte,
        code=first.code + "\n" + second.code,
        size_chars=first.size_chars + second.size_chars + 1,
        kind=ChunkKind.MERGED_GROUP,
        merged_names=merged_names,
        name=combined_name,
        full_name=combined_full_name,
        node_type=None,
        references=first.references + second.references,
    )