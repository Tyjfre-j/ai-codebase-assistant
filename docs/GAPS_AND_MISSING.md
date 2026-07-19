# Ingestion Pipeline — Gaps, Missing Pieces & Open Questions

## 1. `merge_adjacent_defs` is fully dead code
**File:** `app/ingestion/chunking/definition_merger.py`

`merge_adjacent_defs` and `combine_chunks` are never imported or called anywhere in the codebase. `ChunkKind.MERGED_GROUP` is defined but never produced.

Consequences:
- Small adjacent definitions (e.g. many tiny one-line functions) are never merged, so budget enforcement is less effective than designed.
- If re-enabled: `RESOLVABLE_KINDS` would need `MERGED_GROUP` added so merged chunks get their references resolved.
- Also worth checking: `merge_adjacent_defs` doesn't exclude `FUNCTION_SKELETON` — merging a truncated signature with a real definition body would produce nonsensical code.

**Action needed:** decide whether to reinstate (with fixes) or remove the module and `MERGED_GROUP` kind.

## 2. Wildcard imports (`from x import *`) are captured but silently dropped
**Files:** `python_language.py` (QUERY), `import_bindings.py`

The Python `QUERY` captures wildcard imports (`import.wildcard`), but `extract_import_bindings_for_file` never reads this capture. A `from x import *` statement produces **zero bindings**. Any name used later that came via wildcard will fail resolution.

**Action needed:** implement wildcard handling (requires knowing exported names of target module, not currently tracked) or explicitly document as unsupported.

## 3. `iter_source_files` doesn't filter symlinks
**Files:** `source_file_scanner.py` vs. `repository_cloner.py`

The cloner filters symlinks when computing repo size (security threat model: malicious repo symlinking to `/etc/passwd`). `iter_source_files` does not apply the same filter — `os.walk`'s `followlinks=False` stops descending into symlinked directories, but symlinked **files** with matching extensions are yielded and read.

**Action needed:** add `is_symlink()` check to `iter_source_files` or centralize in a shared helper.

## 4. Go structs/interfaces & TS interfaces never get `CLASS_SKELETON` treatment
**Files:** `go_language.py`, `typescript_language.py`

- Go: `CLASS_NODE_TYPES = set()` (empty). Structs and interfaces are captured but never become `CLASS_SKELETON`s.
- TypeScript: `CLASS_NODE_TYPES = {"class_declaration"}` — `interface_declaration` is captured but not included.

**Action needed:** decide if large Go structs/TS interfaces should get skeleton treatment (would need `get_class_member_stub_info` for struct fields/interface method signatures).

## 5. Limited file-extension coverage per language
**File:** `source_parser.py`

Each language registers exactly one extension:
- Python: `.py` only (no `.pyi` stubs)
- Go: `.go` only (no `_test.go` special-casing)
- JavaScript: `.js` only (no `.jsx`, `.mjs`, `.cjs`)
- TypeScript: `.ts` only (no `.tsx`)

**Action needed:** decide if multi-extension support is in scope; would need `LanguageConfig` to support multiple extensions or separate grammars (e.g. tree-sitter-tsx for `.tsx`).

## 6. Repository size limit enforced after full clone
**File:** `repository_cloner.py`

`git clone` runs to completion before size check walks the checkout. For pathologically large repos, the full clone (disk I/O, bandwidth, time) already happened before rejection.

**Action needed:** confirm `GIT_CLONE_FLAGS` includes shallow-clone protections; if not, consider pre-clone size check via `git ls-remote`/API metadata.

## 7. `full_name` docstring invariant doesn't universally hold
**File:** `code_chunk.py`

Docstring states: "when defined_in_class is set, full_name == f'{defined_in_class}.{name}'". But `build_definition_chunk` computes `full_name` from `namespace` first, which can produce a longer dotted path when nested inside both a class and a function.

**Action needed:** fix docstring to reflect actual namespace-aware rule.

## 8. `CodeChunk.docstring` field entirely unpopulated
**File:** `code_chunk.py`

Field exists and is documented as "Reserved for later; always None for now." Nothing populates it.

**Action needed:** implement docstring extraction or remove the field.
