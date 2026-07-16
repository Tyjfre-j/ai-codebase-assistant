# Step 10 — Resolving Import Bindings to File Paths

**Modules:** `app/ingestion/refs/import_bindings.py`,
`app/ingestion/refs/import_resolution.py`
**Entry point:** `extract_import_bindings_for_file(parsed, file_path, project_root, captures)`

## Purpose
For every import statement in a file, work out: what name does the code
actually use to refer to the import (the alias/bound name), and what real
file (or directory, for Go) does that import point to on disk?

## `import_bindings.py` — per-statement binding logic
For each `import.stmt` capture:
- **Explicit bound names exist** (`_bindings_for_statement` finds
  `import.bound_name` captures inside the statement, each paired with its
  optional `import.alias`):
  - If the statement also has a shared `import.module`/`import.relmodule`
    node (a `from X import Y` shape):
    - For languages with `ALLOWS_SUBMODULE_IMPORTS = True` (Python only):
      tries `X.Y` as a **submodule path** first (`app.db.generated.session_queries`
      → its own file), and only falls back to treating `Y` as a symbol
      inside `X`'s own file if that submodule path doesn't resolve to a
      real file. This disambiguates Python's genuinely ambiguous package
      semantics.
    - For JS/TS/Go (no such ambiguity): resolves `X` directly and treats
      `Y` as `ImportKind.NAMED` (a symbol pulled from that resolved file).
  - If there's no separate module node (a plain `import X` shape): `X`
    itself is both the bound name and the module (`ImportKind.MODULE`).
- **No explicit bound-name node at all** (Go's `import "path"`, where the
  grammar has no dedicated bound-name node for the unaliased case): falls
  back to `derive_import_bound_name` (implemented only by the Go module —
  takes the last `/`-separated segment of the import path as the implicit
  package identifier), producing one binding per module path inside a
  possibly-grouped `import (...)` statement.
- **Relative-import detection**: Python's `from . import x` gets a
  dedicated `import.relmodule` capture; JS/TS reuse the same `string` node
  for both relative and absolute imports, so relativity is instead
  inferred from the raw text starting with `.` (`_looks_relative`).

## `import_resolution.py` — turning module text into a real path
- `resolve_relative_import` — strips leading dots, walks up one parent
  directory per extra dot beyond the first, appends the remainder (as a
  dotted-to-slash path if `path_uses_dots`), then tries
  `<path>.<ext>` and, if that doesn't exist, `<path>/<index_filename>`. If
  `resolves_to_directory` (Go) is set, it instead just checks the resulting
  directory exists.
- `resolve_absolute_import` — same file/index-file resolution logic against
  `project_root` instead of the importing file's directory. For Go
  specifically, it first reads `go.mod`'s `module` declaration
  (`_read_declared_module_path`) to strip the repo's own module-path prefix
  before joining with `project_root`; an import that doesn't start with the
  declared module path is treated as an external/third-party package and
  resolves to `None` rather than guessed at.
- `resolve_import_path` — strips surrounding quotes (needed for Go's
  `interpreted_string_literal`, which includes them) and dispatches to one
  of the two functions above based on `is_relative`.

## Output
`dict[str, tuple[resolved_path | None, bound_name, import_kind]]` keyed by
the alias/bound name actually used in code — stored on
`ParsedFileChunks.import_bindings` and consumed by Step 11's
`_resolve_import_reference`.
