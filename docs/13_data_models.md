# Step 13 — Data Models

**Module:** `app/ingestion/code_chunk.py`

## Enums (plain classes of string constants)

### `ChunkKind`
- `DEFINITION` — A function, method, or class that fits within budget (kept whole).
- `CLASS_SKELETON` — A synthetic compact representation of an oversized class: header, class-level code, and method stubs.
- `FUNCTION_SKELETON` — A synthetic compact representation of an oversized function with nested definitions: signature truncated at body.
- `LEFTOVER` — Code that doesn't fit into any definition or skeleton (module-level variables, comments, etc.).
- `MERGED_GROUP` — A group of adjacent small definitions merged together (defined but not currently produced by the pipeline).
- `FILE_OVERVIEW` — A synthetic metadata chunk listing imports and top-level names for a file.

### `RefKind`
- `CALL` — A function or method call.
- `INHERITANCE` — A class extending another (base class reference).

### `RefStatus`
- `LOCAL` — Reference points to a chunk in the same repository.
- `EXTERNAL` — Third-party or standard library import.
- `BUILTIN` — Language built-in (e.g. `print`, `len`, `console.log`).
- `UNRESOLVED` — Could not be resolved to any known chunk.

### `ImportKind`
- `MODULE` — Binds the whole module (e.g. `import os` → "os" binds the module).
- `NAMED` — Binds one specific symbol (e.g. `from os import path` → "path" binds one symbol).

## `RefRecord`
One call or inheritance reference found inside a chunk:
- `text: str` — What was literally written (e.g. `"get_user"`, `"self.get_user"`, `"Base"`).
- `kind: str` — `RefKind.CALL` or `RefKind.INHERITANCE`.
- `points_to: str | None` — The `chunk_id` this reference resolves to, once known.
- `status: str` — `RefStatus.LOCAL`, `EXTERNAL`, `BUILTIN`, or `UNRESOLVED`.

## `CodeChunk`
The central retrievable unit:
- `chunk_id: str` — Stable SHA1-derived id (`stable_chunk_id`).
- `full_name: str` — Name including namespace/class context.
- `name: str` — Just this chunk's own name; `"<anonymous>"` or `"<leftover>"` if unnamed.
- `defined_in_class: str | None` — The class this lives inside, if any.
- `file_path: str` — Which file this chunk came from.
- `start_byte: int` — Where this chunk starts in the source file.
- `end_byte: int` — Where this chunk ends. Same as `start_byte` for skeleton chunks (synthetic code, not a real source slice).
- `language: str` — `"python"`, `"go"`, `"javascript"`, or `"typescript"`.
- `code: str` — The actual text of this chunk (or synthetic stub for skeletons).
- `docstring: str | None` — Reserved for later; always `None` currently.
- `node_type: str | None` — The tree-sitter node type (e.g. `"function_definition"`).
- `kind: str` — `ChunkKind` value.
- `merged_names: list[str] | None` — Original names bundled in a merged group.
- `size_chars: int` — Character count of `code`.
- `parent_chunk_id: str | None` — `chunk_id` of enclosing `CLASS_SKELETON`/`FUNCTION_SKELETON`, or `None` for top-level chunks.
- `references: list[RefRecord]` — Filled at construction time with unresolved records, then mutated in place by Step 11.

## `ParsedFileChunks`
Everything one file contributed:
- `file_path: str`
- `chunks: list[CodeChunk]`
- `import_text: str` — Raw import statement text.
- `import_ranges: list[tuple[int, int]]` — Import byte ranges.
- `import_bindings: dict[str, tuple[str | None, str, str]]` — Maps bound name → (resolved path, original name, import kind).

## `SkippedFile`
- `file_path: str`
- `reason: str` — `"empty"`, `"oversized"`, `"binary"`, `"minified"`, an exception class name, or `"unknown"`.

## `RepositoryChunkResult`
- `files: list[ParsedFileChunks]`
- `skipped: list[SkippedFile]`
- `.skip_counts_by_reason() -> dict[str, int]` — Tallies skipped files by reason.
