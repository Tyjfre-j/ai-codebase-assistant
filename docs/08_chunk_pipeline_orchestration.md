# Step 8 — Per-File Chunk Pipeline

**Module:** `app/ingestion/chunking/chunk_pipeline.py`
**Entry point:**
`chunk_file(file_path, parsed, budget) -> (chunks, import_text, import_ranges, captures)`

## Purpose
Ties Steps 4–7 together for a single already-parsed file.

## Sequence
1. **Guard the budget** — `budget <= 0` raises `InvalidChunkBudgetError`
   immediately (defensive; the repository-level orchestrator also checks
   this once up front before touching any file).
2. **Guard against syntax errors** — `parsed.tree.root_node.has_error`
   raises `MalformedSourceError` and the file is skipped entirely rather
   than chunked from an unreliable tree. This is an all-or-nothing check:
   one syntax error anywhere in the file discards the whole file's chunks,
   there's no partial/best-effort chunking of the valid portions.
3. **Run captures** (Step 4) → `captures` dict.
4. **Collect definition node ids** — the union of node ids across every
   `DEF_CAPTURES` name present in `captures`.
5. **Look up `class_node_types`** for this language (falls back to an empty
   set if the language doesn't define `CLASS_NODE_TYPES`).
6. **Classify** (Step 5) → `chunk_candidates`.
7. **Build chunks** (Step 6) — dispatches each candidate to the matching
   `build_*_chunk` function by `candidate_kind`; `LEFTOVER` candidates are
   instead collected into `leftover_groups` for batch processing.
8. **Group leftovers** (Step 7) → `leftover_chunks, import_text, import_ranges`.
9. Returns `definition_chunks + leftover_chunks` (definitions first, then
   leftovers, in that concatenation order — **not** original document
   order across the two categories) alongside the import metadata and the
   raw `captures` dict (reused by Step 10 so imports aren't re-queried).

## Output
Everything `repo_chunker` needs for one file: the chunk list, the import
text/ranges pair, and the captures dict.
