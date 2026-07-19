# Step 8 — Per-File Chunk Pipeline

**Module:** `app/ingestion/chunking/chunk_pipeline.py`
**Entry point:** `chunk_file(file_path, parsed, budget) -> (chunks, import_text, import_ranges, captures)`

## Purpose
Ties Steps 4–7 together for a single already-parsed file.

## Sequence
1. **Guard the budget** — `budget <= 0` raises `InvalidChunkBudgetError`.
2. **Guard against syntax errors** — `parsed.tree.root_node.has_error` raises `MalformedSourceError`; the file is skipped entirely.
3. **Run captures** (Step 4) → `captures` dict.
4. **Collect definition node ids** — union of node ids across all `DEF_CAPTURES` names in `captures`.
5. **Look up `class_node_types`** for this language (falls back to empty set).
6. **Classify** (Step 5) → `chunk_candidates`.
7. **Build chunks** (Step 6) — dispatches each candidate by `candidate_kind`:
   - `DEFINITION` → `build_definition_chunk`
   - `CLASS_SKELETON` → `build_class_skeleton_chunk`
   - `FUNCTION_SKELETON` → `build_function_skeleton_chunk`
   - `LEFTOVER` → collected into `leftover_groups` for batch processing

   During this step, `node_id_to_chunk_id` is populated so parent chunk IDs can be resolved. `top_level_names` collects names of all top-level chunks (skeletons and whole definitions) for the file overview.

8. **Group leftovers** (Step 7) → `leftover_chunks, import_text, import_ranges`.
9. **Build file overview** — `build_file_overview_chunk` with `top_level_names` and `import_text`.
10. **Assemble final chunks** — `[overview] + definition_chunks + leftover_chunks`.

## Output
- `chunks: list[CodeChunk]` — all chunks for this file (overview first, then definitions/skeletons, then leftovers).
- `import_text: str` — raw import text.
- `import_ranges: list[tuple[int, int]]` — import byte ranges.
- `captures: dict[str, list[Node]]` — raw query captures (reused by Step 10).
