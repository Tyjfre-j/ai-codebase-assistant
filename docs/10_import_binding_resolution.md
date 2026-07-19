# Step 10 — Resolving Import Bindings to File Paths

**Modules:** `app/ingestion/refs/import_bindings.py`, `app/ingestion/refs/import_resolution.py`
**Entry point:** `extract_import_bindings_for_file(parsed, file_path, project_root, captures)`

## Purpose
For every import statement in a file, determine: what name does the code use to refer to the import (alias/bound name), and what real file (or directory, for Go) does it point to on disk?

## `import_bindings.py` — per-statement binding logic

For each `import.stmt` capture:

### Explicit bound names exist (`_bindings_for_statement`)
Finds `import.bound_name` captures inside the statement, each paired with optional `import.alias`.

**With shared module node (`from X import Y` shape):**
- **Python** (`ALLOWS_SUBMODULE_IMPORTS = True`): tries `X.Y` as a **submodule path** first, falls back to treating `Y` as a symbol inside `X`'s own file if submodule doesn't exist.
- **JS/TS/Go** (no such ambiguity): resolves `X` directly, treats `Y` as `ImportKind.NAMED`.

**Without module node (`import X` shape):**
`X` itself is both bound name and module (`ImportKind.MODULE`).

### No explicit bound-name node (Go's `import "path"`)
Falls back to `derive_import_bound_name` (Go only — takes last `/`-separated segment as implicit package identifier), producing one binding per module path.

### Relative-import detection
- Python: `from . import x` gets dedicated `import.relmodule` capture.
- JS/TS: relativity inferred from raw text starting with `.` (`_looks_relative`).

## `import_resolution.py` — turning module text into a real path

### `resolve_relative_import`
Strips leading dots, walks up directories, appends remainder (dotted-to-slash if `path_uses_dots`), tries `<path>.<ext>` then `<path>/<index_filename>`.

### `resolve_absolute_import`
Same against `project_root`. For Go: reads `go.mod`'s `module` declaration to strip repo's own module-path prefix first; imports not matching declared module path are treated as external (`None`).

### `resolve_import_path`
Strips quotes and dispatches to relative or absolute resolver.

## Output
`dict[str, tuple[resolved_path | None, bound_name, import_kind]]` keyed by alias/bound name actually used in code — stored on `ParsedFileChunks.import_bindings` and consumed by Step 11's `_resolve_import_reference`.
