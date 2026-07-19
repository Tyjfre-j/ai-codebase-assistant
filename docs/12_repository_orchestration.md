# Step 12 — Repository-Level Orchestration

**Module:** `app/ingestion/repo_chunker.py`
**Entry point:** `chunk_repository(root, max_size_mb, budget) -> RepositoryChunkResult`

## Purpose
Top-level driver: walk the repo, chunk every eligible file, resolve references across all of them, and report what got skipped and why.

## Sequence
1. **Budget guard** — `budget <= 0` raises `InvalidChunkBudgetError` before any file is touched.
2. **Parser init** — one `CodeParser()` for the whole run (loads every grammar and compiles every query once).
3. **Per-file loop** (`iter_source_files` — Step 2a):
   a. `validate_file_thru_path` (Step 2b) — skip on empty/oversized.
   b. Read file bytes; `OSError` recorded as skip.
   c. `validate_file_thru_content` (Step 2c) — skip on binary/minified.
   d. Parse (Step 3), chunk (Steps 4–8), extract import bindings (Step 10) — wrapped in `try` catching `MalformedSourceError`, `TreeSitterParseError`, `ChunkExtractionError`.
   e. On success, append `ParsedFileChunks` to `results`.
4. **Repo-wide reference resolution** (Step 11) — runs exactly once after all files are chunked.
5. **Result assembly** — `RepositoryChunkResult(files=results, skipped=skipped)`.

## Error-handling philosophy
Per-file failures are contained and reported, never propagated. Only structural run-level problems (`budget <= 0`) raise before any work starts.

## Output
`RepositoryChunkResult`:
- `files: list[ParsedFileChunks]` — one entry per successfully chunked file, with fully-resolved references.
- `skipped: list[SkippedFile]` — every file that didn't make it in, with a reason string.
- `.skip_counts_by_reason()` — convenience rollup for logging/reporting.
