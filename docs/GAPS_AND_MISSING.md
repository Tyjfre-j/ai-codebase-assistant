# Ingestion Pipeline — Gaps, Missing Pieces & Open Questions

This is a read-only audit of `ingestion_dump.txt` (23 files, the
`app/ingestion/*` tree). No tests were run — findings are from static
reading of the code and cross-referencing call sites only. Ordered roughly
by severity.

---

## 1. `merge_adjacent_defs` is fully dead code
**File:** `app/ingestion/chunking/definition_merger.py`

`merge_adjacent_defs` and `combine_chunks` are never imported or called
anywhere in the 23 files in this dump — not from `chunk_pipeline.py`, not
from `repo_chunker.py`, nowhere. Confirmed by grepping the whole tree for
`merge_adjacent_defs` / `definition_merger`.

Consequences:
- `ChunkKind.MERGED_GROUP` is defined in `code_chunk.py` and referenced in
  comments/docstrings elsewhere (e.g. `CodeChunk.merged_names`'s docstring,
  `resolver.py`'s `RESOLVABLE_KINDS` exclusion) as if it's a real, produced
  chunk kind — it is not. No chunk in the current pipeline will ever have
  `kind == MERGED_GROUP`.
- Small adjacent definitions (e.g. a file of many tiny one-line functions)
  are never merged, so the "respect the size budget" cost-saving this
  module exists for isn't happening. If this used to run and was
  disconnected during a refactor, that's a regression; if it's WIP for a
  planned feature, it's incomplete integration.
- If it *were* wired back in: `resolver.py`'s `RESOLVABLE_KINDS` does not
  include `MERGED_GROUP`, so merged chunks would silently never get their
  `references[*].points_to` resolved even though `combine_chunks` carefully
  concatenates `first.references + second.references` — that concatenated
  list would stay permanently unresolved. Wiring this back in needs both
  the call-site integration *and* a `RESOLVABLE_KINDS` update.
- Also worth checking before re-enabling: `merge_adjacent_defs` merges any
  two adjacent non-`CLASS_SKELETON` chunks, without excluding
  `FUNCTION_SKELETON`. A `FUNCTION_SKELETON` chunk's `code` is a truncated
  signature ending in `"..."` — merging that with a following real
  `DEFINITION` chunk's full body would produce a chunk of code that doesn't
  actually parse/read sensibly as a unit.

**Action needed:** decide whether merging should be reinstated (and where
in `chunk_pipeline.py` it belongs — likely after `group_leftovers`, before
the file's chunks are returned), or whether the module + `MERGED_GROUP`
should be removed to stop the schema implying a feature that doesn't exist.

---

## 2. Wildcard imports (`from x import *`) are captured but silently dropped
**Files:** `python_language.py` (QUERY), `import_bindings.py`

The Python `QUERY` explicitly captures wildcard imports:
```
(import_from_statement
  module_name: (dotted_name) @import.module
  (wildcard_import) @import.wildcard
) @import.stmt
```
But `extract_import_bindings_for_file` never reads the `import.wildcard`
capture at all. For a `from x import *` statement:
- `_bindings_for_statement` finds no `import.bound_name` (there isn't one),
  so `statement_bindings` is empty.
- `derive_bound_name` is `None` for Python (only Go implements it), so the
  `elif derive_bound_name is not None` fallback branch also doesn't fire.
- Net effect: the statement produces **zero bindings**. Any name used later
  in the file that actually came in via the wildcard import will fail every
  resolution step in `resolver.py` and end up `RefStatus.UNRESOLVED`
  (or, worse, silently mis-resolve to an unrelated same-named symbol
  elsewhere in the repo via the global fallback).

**Action needed:** either implement wildcard handling (would require
knowing the *exported* names of the target module, which isn't tracked
anywhere in this pipeline) or explicitly document that wildcard imports are
an unsupported/best-effort case.

---

## 3. `iter_source_files` doesn't filter symlinks — inconsistent with the cloner's own threat model
**Files:** `source_file_scanner.py` vs. `repository_cloner.py`

`repository_cloner.py` explicitly filters out symlinks when computing repo
size, with a comment stating exactly why: *"a malicious repo could contain
symlinks to sensitive host files (/etc/passwd, /proc/self/environ, etc.)"*.

`iter_source_files` (used immediately afterward, on the very same cloned
checkout, to decide which files actually get *read and parsed*) does not
apply the same filter. `os.walk`'s `followlinks=False` default stops it
from *descending into* a symlinked directory, but a symlinked **file**
whose target has a matching extension (e.g. a `.py` symlink pointing to
`/etc/passwd` renamed, or to any file elsewhere on the host) is yielded and
then opened and read as source content in `repo_chunker.chunk_repository`.

This means the exact attack the cloner's comment is defending against is
still reachable through the file-scanning stage, just not through the
size-accounting stage. Given the cloner author clearly considered this
threat model, this looks like an oversight rather than an accepted risk.

**Action needed:** add an `is_symlink()` check to `iter_source_files` (or
centralize the symlink filter in one shared helper used by both stages).

---

## 4. Interfaces are never treated as class-like skeletons (TS), and Go structs/interfaces never are either
**Files:** `go_language.py`, `typescript_language.py`, `chunk_candidates.py`

- Go: `CLASS_NODE_TYPES = set()` — empty. Both `class.def` (struct) and
  `interface.def` captures exist in the `QUERY`, feed into
  `definition_ids`, and are eligible for `DEFINITION`/`FUNCTION_SKELETON`
  treatment in `_walk`, but **never** for `CLASS_SKELETON` treatment, since
  that branch is gated on `node.type in class_node_types`. A large Go
  struct with many fields, or a large interface with many method
  signatures, will either fit the budget as one `DEFINITION` chunk or (if
  oversized with no nested definition inside it — which structs/interfaces
  typically don't have) fall through to the "oversized, keep it anyway"
  branch in `chunk_candidates.py`, producing one very large chunk with no
  compact stub form. Contrast with Python/JS/TS classes, which get a
  proper compact `CLASS_SKELETON`.
- TypeScript: `CLASS_NODE_TYPES = {"class_declaration"}` — `interface_declaration`
  is captured (`interface.def`) but not included, so the same gap applies
  to large TS interfaces specifically (classes are handled correctly).

**Action needed:** decide if this is intentional (interfaces/structs may be
considered "small enough to never need skeletons" — untrue in practice for
large generated/DTO-style interfaces) or should be added to
`CLASS_NODE_TYPES` for Go and TS, with corresponding
`get_class_member_stub_info` support for interface members/struct fields
(currently only implemented for methods/arrow-function fields, not plain
struct fields or interface method signatures).

---

## 5. Limited file-extension coverage per language
**File:** `source_parser.py` (registry), each `*_language.py`'s `FILE_EXTENSION`

Each language registers exactly **one** extension:
- Python: `.py` only (no `.pyi` stub files).
- Go: `.go` only (no `_test.go` special-casing, which is fine, but also no
  handling of build-tag-gated files beyond what tree-sitter naturally
  parses).
- JavaScript: `.js` only — **no `.jsx`, `.mjs`, or `.cjs`**. A codebase with
  JSX in `.jsx` files, or explicit ESM/CJS extensions, will have those
  files entirely invisible to `iter_source_files` (wrong extension → never
  yielded, no skip reason logged either since it's filtered before
  `SkippedFile` tracking even begins).
- TypeScript: `.ts` only — **no `.tsx`**. Same consequence for any React
  TypeScript codebase.

**Action needed:** decide whether multi-extension languages are in scope;
if so, `LanguageConfig`/`load_languages` currently assumes a strict 1:1
`extension -> language` mapping (`configs[module.FILE_EXTENSION] = ...`),
so supporting `.jsx`/`.tsx`/`.mjs` would need either a list of extensions
per language or a separate grammar/config per extension (tree-sitter-tsx is
a genuinely different grammar from tree-sitter-typescript, not just an
extension alias).

---

## 6. Repository size limit is enforced *after* the full clone completes
**File:** `repository_cloner.py`, `_do_clone`

`git clone` (with whatever `GIT_CLONE_FLAGS` specifies — not visible in
this dump, so it's unknown whether a shallow/`--depth` flag is already in
use) runs to completion, and only afterward does the code walk the checkout
and sum file sizes to compare against `MAX_REPO_SIZE_MB`. For a
pathologically large or malicious repository, this means the full clone
(disk I/O, bandwidth, time) already happened before the size check can
reject it — the guard limits what gets *chunked*, not what gets *cloned*.
Whether this is an accepted trade-off depends on `GIT_CLONE_FLAGS`
(untested/not in this dump) and on `CLONE_TIMEOUT_SECONDS` acting as the
real backstop for runaway clones.

**Action needed:** confirm `GIT_CLONE_FLAGS` includes shallow-clone
protections; if not, consider a size check via a lighter-weight mechanism
(e.g. `git ls-remote`/API metadata) before committing to a full clone.

---

## 7. `full_name == f"{defined_in_class}.{name}"` invariant doesn't universally hold
**File:** `code_chunk.py` (docstring) vs. `chunk_factory.py`

`CodeChunk`'s own docstring states: *"NOTE: when defined_in_class is set,
full_name == f'{defined_in_class}.{name}'"*. But
`build_definition_chunk`/`build_function_skeleton_chunk` actually compute:
```python
if namespace:
    full_name = ".".join(namespace + [name])
elif defined_in_class:
    full_name = f"{defined_in_class}.{name}"
else:
    full_name = name
```
For any language/case where `get_namespace` returns a non-empty list *and*
`defined_in_class` is also set (e.g. a Python method nested inside a nested
class inside a function — `get_namespace` walks up through both
`class_definition` and `function_definition` types), `full_name` becomes
the full dotted namespace path, which will generally **not** equal
`f"{defined_in_class}.{name}"` if there's more than one level of nesting
captured in `namespace`. The documented invariant is only exactly true in
the simple one-level-of-class-nesting case.

**Action needed:** either fix the docstring to reflect the actual
(more general, namespace-aware) rule, or confirm this is intentional and
just under-documented.

---

## 8. Files referenced but not included in this dump
Several modules imported throughout this codebase are referenced but their
source wasn't part of `ingestion_dump.txt`, so this audit could not verify
their contents directly — only their usage:
- `app/core/constants.py` — `DEFAULT_CHUNK_BUDGET_CHARS`,
  `DEFAULT_MAX_FILE_SIZE_MB`, `ALLOWED_REPOSITORY_HOSTS`, `BYTES_PER_MB`,
  `CLONE_ERROR_MESSAGE_MAX_CHARS`, `CLONE_TIMEOUT_SECONDS`,
  `GIT_CLONE_FLAGS`, `MAX_REF_LENGTH`, `MAX_REPO_SIZE_MB`,
  `CHUNK_ID_HEX_LENGTH`, `_SKIP_DIRS`.
- `app/core/exceptions.py` — every custom exception type raised throughout
  (`ChunkExtractionError`, `InvalidChunkBudgetError`, `MalformedSourceError`,
  `TreeSitterParseError`, `LanguageLoadError`, `UnsupportedFileExtensionError`,
  `UnregisteredLanguageError`, `ChunkDecodeError`, `FileAccessError`,
  `CloneTimeoutError`, `InvalidRepositoryURLError`, `InvalidRefError`,
  `EmptyRepositoryError`, `RepositoryTooLargeError`).

**Action needed if a fuller audit is wanted:** supply these two files —
in particular, `GIT_CLONE_FLAGS` and `_SKIP_DIRS` materially affect the
security/coverage findings above (#3, #6) and can't be fully assessed
without them.

---

## 9. No handling for docstring extraction despite a dedicated field
**File:** `code_chunk.py`

`CodeChunk.docstring` exists as a field and is explicitly commented
*"Reserved for later; always None for now."* Nothing in the 23 files reads
or populates it — confirmed, no assignment to `.docstring` anywhere in the
dump other than the `None` literals in the four `build_*_chunk` functions.
This isn't a bug (it's documented as intentionally deferred), but it's
worth listing here since "what's missing/not done" was explicitly asked
for — this is the one field in the core schema that's explicitly
acknowledged as incomplete by its own author.

---

## Summary table

| # | Finding | Severity | Type |
|---|---|---|---|
| 1 | `merge_adjacent_defs` dead code, never called | High | Missing integration |
| 2 | Python wildcard imports (`import *`) silently unresolved | Medium | Functional gap |
| 3 | `iter_source_files` doesn't filter symlinks (cloner does) | Medium–High | Security inconsistency |
| 4 | Go structs/interfaces & TS interfaces never get `CLASS_SKELETON` treatment | Low–Medium | Functional gap |
| 5 | Only one file extension per language (`.js`≠`.jsx`, `.ts`≠`.tsx`, etc.) | Medium | Coverage gap |
| 6 | Repo size enforced after full clone, not before | Low–Medium | Resource-exhaustion risk (depends on unseen constants) |
| 7 | `full_name` docstring invariant inaccurate for namespaced nesting | Low | Documentation/consistency |
| 8 | `app/core/constants.py` and `app/core/exceptions.py` not in dump | N/A | Audit-scope limitation |
| 9 | `CodeChunk.docstring` field entirely unpopulated | Low | Explicitly deferred, not a bug |
