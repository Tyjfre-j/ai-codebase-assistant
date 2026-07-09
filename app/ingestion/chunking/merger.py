from dataclasses import replace

from app.ingestion.chunk_model import CodeChunk

MAX_GAP_BYTES = 2  # allowance for a blank line between mergeable siblings

def merge_adjacent_defs(chunks: list[CodeChunk], budget: int) -> list[CodeChunk]:
    merged: list[CodeChunk] = []
    buffer: CodeChunk | None = None

    for c in chunks:
        if c.chunk_kind == "class_skeleton":
            if buffer is not None:
                merged.append(buffer)
                buffer = None
            merged.append(c)  # skeletons pass through untouched, never merged
            continue
        if buffer is None:
            buffer = c
            continue
        contiguous = c.start_byte - buffer.end_byte <= MAX_GAP_BYTES
        if contiguous and (buffer.size_chars + c.size_chars) <= budget:
            buffer = combine_chunks(buffer, c)
        else:
            merged.append(buffer)
            buffer = c
    if buffer is not None:
        merged.append(buffer)
    return merged

def combine_chunks(a: CodeChunk, b: CodeChunk) -> CodeChunk:
    names = (a.merged_symbols or [a.symbol_name]) + (b.merged_symbols or [b.symbol_name])
    return replace(
        a,
        end_byte=b.end_byte,
        content=a.content + "\n" + b.content,
        size_chars=a.size_chars + b.size_chars + 1,
        chunk_kind="merged_group",
        merged_symbols=names,
        symbol_name=f"{a.symbol_name}+{b.symbol_name}",
        qualified_name=f"{a.qualified_name}+{b.qualified_name}",
    )