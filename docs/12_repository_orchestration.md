# Step 12 — Repository-Level Orchestration

**Module:** `app/ingestion/repo_chunker.py`
**Entry point:** `chunk_repository(root, max_size_mb, budget) -> RepositoryChunkResult`

## Purpose
The top-level driver that ties every earlier step together into one call:
walk the repo, chunk every eligible file, resolve references across all of
them, and report what got skipped and why.

## Sequence
1. **Budget guard** — `budget <= 0` raises `InvalidChunkBudgetError` before
   any file is touched (fail fast, don't waste time parsing).
2. **Parser init** — one `CodeParser()` for the whole run (loads every
   grammar and compiles every query once), and pulls the set of supported
   extensions from `parser.language_configs.keys()`.
3. **Per-file loop** (`iter_source_files` — Step 2a):
   a. `validate_file_thru_path` (Step 2b) — skip on empty/oversized,
      recording a `SkippedFile(reason=...)`.
   b. Read the file's bytes; an `OSError` here is also recorded as a
      skip (`type(e).__name__` as the reason) rather than aborting the
      whole run.
   c. `validate_file_thru_content` (Step 2c) — skip on binary/minified.
   d. Parse (Step 3), chunk (Steps 4–8), and extract import bindings
      (Step 10) — wrapped in one `try` that catches `MalformedSourceError`,
      `TreeSitterParseError`, and `ChunkExtractionError`, all treated as
      skips (again, one bad file doesn't abort the run).
   e. On success, append a `ParsedFileChunks` (file path, chunks, import
      text/ranges, import bindings) to `results`.
4. **Repo-wide reference resolution** (Step 11) — runs exactly once, after
   every file has been individually chunked, since resolution needs the
   whole-repo symbol/inheritance indexes.
5. **Result assembly** — `RepositoryChunkResult(files=results,
   skipped=skipped)`; if anything was skipped, logs one warning line with
   counts grouped by reason (`skip_counts_by_reason`).

## Error-handling philosophy
Per-file failures (bad syntax, oversized, binary, OS errors) are contained
and reported, never propagated — a single problematic file degrades the
result, it doesn't kill the whole ingestion run. Only structural,
run-level problems (`budget <= 0`) raise before any work starts.

## What's conspicuously *not* called here
`merge_adjacent_defs` (`app/ingestion/chunking/definition_merger.py`) is
never invoked anywhere in this sequence, or anywhere else in the codebase.
See the gaps/missing document — this is the single most significant
finding of this audit.

## Output
`RepositoryChunkResult`:
- `files: list[ParsedFileChunks]` — one entry per successfully chunked
  file, with fully-resolved references.
- `skipped: list[SkippedFile]` — every file that didn't make it in, with a
  reason string.
- `.skip_counts_by_reason()` — a convenience rollup for logging/reporting.
