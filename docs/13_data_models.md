# Step 13 — Data Models

**Module:** `app/ingestion/code_chunk.py`

This module has no logic of its own — it's the shared vocabulary every other
stage reads and writes. Documented last here because it's easiest to
understand once you've seen how each field gets populated.

## Enums (plain classes of string constants, not `enum.Enum`)
- **`ChunkKind`** — `DEFINITION`, `CLASS_SKELETON`, `FUNCTION_SKELETON`,
  `LEFTOVER`, `MERGED_GROUP` (this last one is defined but never produced —
  see the gaps document).
- **`RefKind`** — `CALL`, `INHERITANCE`.
- **`RefStatus`** — `LOCAL`, `EXTERNAL`, `BUILTIN`, `UNRESOLVED`.
- **`ImportKind`** — `MODULE` (binds a whole module), `NAMED` (binds one
  specific symbol out of a module).

## `RefRecord`
One call or inheritance reference found inside a chunk: `text` (as written
at the call site), `kind`, `points_to` (chunk id once resolved, else
`None`), `status` (defaults to `UNRESOLVED` until Step 11 runs).

## `CodeChunk`
The central retrievable unit. Key fields worth calling out explicitly:
- `chunk_id` — stable SHA1-derived id (Step 6/9's `stable_chunk_id`).
- `full_name` vs `name` — `full_name` includes namespace/class context;
  `name` is just the chunk's own identifier. The dataclass comment notes
  `full_name == f"{defined_in_class}.{name}"` **when** `defined_in_class`
  is set — but this invariant does not universally hold once a language's
  `get_namespace` is involved (see gaps document).
- `end_byte` — genuinely equal to `start_byte` for skeleton chunks (this is
  documented and intentional, not a bug — skeletons hold synthetic text,
  not a real source slice).
- `docstring` — reserved, always `None` in the current pipeline; nothing
  populates it yet.
- `merged_names` — only meaningful for `ChunkKind.MERGED_GROUP`, which is
  never actually produced by the current pipeline.
- `references` — defaults to an empty list; populated at chunk-construction
  time (Step 6/9) with unresolved records, then mutated in place by Step 11.

## `ParsedFileChunks`
Everything one file contributed: its chunk list, raw import text/ranges,
and `import_bindings` (populated in Step 10, defaults to `{}` otherwise).

## `SkippedFile`
`file_path` + a free-form `reason` string (one of the `InvalidFileReason`
enum values, or an exception class name, or `"unknown"` if a `path_check`
somehow reports invalid without a reason).

## `RepositoryChunkResult`
The final top-level output: `files`, `skipped`, and a
`skip_counts_by_reason()` helper that tallies `skipped` by `reason`.
