# Step 11 — Cross-Repository Reference Resolution

**Module:** `app/ingestion/refs/resolver.py`
**Entry point:** `resolve_all_chunk_references(all_parsed_chunks: list[ParsedFileChunks])`

## Purpose
Once every file in the repo has been chunked (Steps 1–10), this is the one
pass that turns each chunk's raw `RefRecord.text` values into concrete
`points_to` chunk ids, using indexes built from the *whole* repository at
once.

## Indexes built once, up front
- `build_definition_index` — global `name/full_name -> [chunk_id, ...]`
  across every chunk whose `kind` is in `RESOLVABLE_KINDS = (DEFINITION,
  CLASS_SKELETON, FUNCTION_SKELETON)`.
- `build_file_symbol_index` — same, but bucketed per `file_path` first (used
  for same-file and import-target lookups, avoiding a linear scan of all
  chunks per reference).
- `build_dir_symbol_index` — same, bucketed per directory (`os.path.dirname`)
  — needed because Go imports resolve to a package *directory* containing
  several files, not one specific file.
- `build_inheritance_graph` — `class_chunk_id -> [parent_chunk_id, ...]`,
  built directly from each `CLASS_SKELETON` chunk's already-extracted
  `INHERITANCE` references.

## Resolution order, per reference (`resolve_chunk_references`)
Tried in this exact order, first hit wins:
1. **Self reference** (`_resolve_self_reference`) — for `self.`/`cls.`/
   `this.`-prefixed text, only if the chunk has a `defined_in_class`. Looks
   up `{class}.{rest}` in the current file first, falling back to the
   global index only if the same-file lookup isn't a unique hit. If not
   found on the class itself, walks the inheritance graph breadth-first
   (with a `visited` set for cycle protection) checking each ancestor
   class's own file for a `{ancestor}.{rest}` match — an MRO-like walk,
   though it does not implement Python's actual C3-linearization MRO, just
   BFS over declared parents.
2. **Import reference** (`_resolve_import_reference`) — splits `text` on
   the first `.` into `root` + `rest`, looks up `root` in the file's
   `import_bindings`. If the binding's `import_kind` is `MODULE`, the real
   target symbol is whatever follows the root (`os.path.join` → looks for
   `path.join` inside `os`'s resolved file); if `NAMED`, the bound name
   itself is the target and anything after the dot is just an attribute
   access, not a further lookup. Tries the resolved path as a specific file
   first, then as a directory (Go's case).
3. **Same-file reference** (`_resolve_same_file_reference`) — plain
   unqualified name lookup within the chunk's own file.
4. **Global fallback** (`_resolve_global_reference`) — lookup across the
   entire repository-wide index.

All four lookups require an **exact, unique** match (`len(candidates) == 1`)
— any ambiguity (multiple functions with the same name anywhere applicable)
results in no resolution rather than a guess.

## Cross-language guard
If a reference does resolve to a chunk, but that chunk's `language` differs
from the referencing chunk's language, the match is discarded
(`points_to = None`) — this prevents accidental resolution between, say, a
Python function and a same-named JS function.

## Status assignment
When nothing resolves, `RefRecord.status` is set based on:
- `RefStatus.EXTERNAL` if the reference's root name is a *resolved* import
  binding whose target path is `None` (i.e. a real recognized import, just
  pointing outside the repo — third-party/stdlib).
- `RefStatus.BUILTIN` if the root name is in the language's `BUILTINS` set.
- `RefStatus.UNRESOLVED` otherwise.

## Which chunks get resolved at all
Only chunks whose `kind` is in `RESOLVABLE_KINDS` — `DEFINITION`,
`CLASS_SKELETON`, `FUNCTION_SKELETON` — go through
`resolve_chunk_references`. `LEFTOVER` chunks never have references in the
first place (Step 6 never calls `extract_reference_records` for them), so
this is a non-issue there. `MERGED_GROUP` is a real gap — see the
gaps/missing document.

## Output
No return value — `resolve_chunk_references` mutates each
`RefRecord.points_to`/`.status` **in place**, so after this call every
chunk's `references` list reflects final resolution state.
