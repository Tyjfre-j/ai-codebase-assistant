from dataclasses import replace

from app.ingestion.code_chunk import CodeChunk

MAX_GAP_BYTES = 2  # allowance for a blank line between mergeable siblings


def merge_adjacent_defs(chunks: list[CodeChunk], budget: int) -> list[CodeChunk]:
    """Merge adjacent definition chunks while respecting the size budget."""
    merged: list[CodeChunk] = []
    buffer: CodeChunk | None = None

    for chunk in chunks:
        if chunk.kind == "class_skeleton":
            if buffer is not None:
                merged.append(buffer)
                buffer = None
            merged.append(chunk)  # skeletons pass through untouched, never merged
            continue
        if buffer is None:
            buffer = chunk
            continue
        is_contiguous = chunk.start_byte - buffer.end_byte <= MAX_GAP_BYTES
        if is_contiguous and (buffer.size_chars + chunk.size_chars) <= budget:
            buffer = combine_chunks(buffer, chunk)
        else:
            merged.append(buffer)
            buffer = chunk
    if buffer is not None:
        merged.append(buffer)
    return merged


def combine_chunks(first: CodeChunk, second: CodeChunk) -> CodeChunk:
    """Return a single chunk with metadata from two adjacent definitions."""
    merged_names = (
        first.merged_names or [first.name]
    ) + (
        second.merged_names or [second.name]
    )
    return replace(
        first,
        end_byte=second.end_byte,
        code=first.code + "\n" + second.code,
        size_chars=first.size_chars + second.size_chars + 1,
        kind="merged_group",
        merged_names=merged_names,
        name=f"{first.name}+{second.name}",
        full_name=f"{first.full_name}+{second.full_name}",
        node_type=None,
    )
