# Step 7 — Splitting Leftovers into Imports & Budgeted Chunks

**Module:** `app/ingestion/chunking/leftover_chunks.py`
**Entry point:** `group_leftovers(leftover_groups, captures, file_path, parsed, budget, node_id_to_chunk_id)`

## Purpose
Each `LEFTOVER` candidate from Step 5 is a bundle of adjacent non-definition nodes — may include import statements mixed with module-level code. This stage separates imports into metadata and packs the rest into budget-respecting `CodeChunk`s.

## Algorithm, per leftover group
1. Identify import nodes (`node.id in import_ids`, from `import.stmt` capture).
2. Walk the group in order, splitting into `segments`: maximal runs of *non-import* nodes; hitting an import closes the current segment and starts a new one.
3. Pack segments greedily: add segments to current buffer while running byte-size stays within `budget`; exceeding budget flushes the buffer as one `build_leftover_code_chunk` call. A single segment larger than budget becomes its own (over-budget) chunk.
4. Import nodes across all groups are collected into one `imports` list in document order.

## Parent chunk linkage
`parent_chunk_id` is resolved via `node_id_to_chunk_id`, populated by the caller as it builds chunks in document order. This guarantees the parent (skeleton) is built before any of its children.

- Top-level leftovers → `parent_chunk_id = None` (no parent, they are top-level)
- Leftovers inside a class/function skeleton → `parent_chunk_id = skeleton.chunk_id`

## Output
- `leftover_chunks: list[CodeChunk]` — budgeted, import-free code chunks.
- `import_text: str` — all import statements joined with `"\n"`.
- `import_ranges: list[tuple[start_byte, end_byte]]` — one entry per import statement.

`import_text`/`import_ranges` are returned through `chunk_file` as metadata on `ParsedFileChunks`. They are not used for resolution directly — Steps 10–11 re-derive bindings from the `captures` dict.
