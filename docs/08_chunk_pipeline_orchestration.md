# Step 8 — Per-File Chunk Pipeline

**Module:** `app/ingestion/chunking/chunk_pipeline.py`
**Entry point:** `chunk_file(file_path, parsed, budget, skeleton_threshold) -> (chunks, import_text, import_ranges, captures)`

## Purpose
Ties chunking stages together for a single already-parsed file.

## Sequence
1. **Guard limits** — `budget <= 0` or `skeleton_threshold <= 0` raises `InvalidChunkBudgetError`.
2. **Guard against syntax errors** — `parsed.tree.root_node.has_error` raises `MalformedSourceError`; the file is skipped entirely.
3. **Run captures** → `captures` dict.
4. **Collect node ids** — gathers all definition node IDs and import node IDs.
5. **Extract import metadata** — runs `extract_import_metadata(captures, parsed)` to get `import_text` and `import_ranges`.
6. **Build File Skeleton (if oversized)** — if the file size exceeds `skeleton_threshold`, `build_file_skeleton_chunk` produces a `FILE_SKELETON` summarizing the entire file.
7. **Classify Candidates** — `walk_top_level()` yields `DEFINITION` and `DEFINITION_SKELETON` candidates.
8. **Build CodeChunks** — dispatches each candidate by `candidate_kind`:
   - `DEFINITION` → `build_definition_chunk`
   - `DEFINITION_SKELETON` → `build_skeleton_chunk`

   Parent chunk IDs are assigned automatically based on lexical nesting, pointing up to the file skeleton or enclosing definition skeleton.

## Output
- `chunks: list[CodeChunk]` — all chunks for this file.
- `import_text: str` — raw import text.
- `import_ranges: list[tuple[int, int]]` — import byte ranges.
- `captures: dict[str, list[Node]]` — raw query captures (reused later by reference resolution stages).
