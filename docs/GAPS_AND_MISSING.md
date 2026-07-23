# Ingestion Pipeline — Gaps, Missing Pieces & Open Questions

## 1. Wildcard imports (`from x import *`) are captured but silently dropped
**Files:** `python_language.py` (QUERY), `import_bindings.py`

The Python `QUERY` captures wildcard imports (`import.wildcard`), but `extract_import_bindings_for_file` never reads this capture. A `from x import *` statement produces **zero bindings**. Any name used later that came via wildcard will fail resolution.

**Action needed:** implement wildcard handling (requires knowing exported names of target module, not currently tracked) or explicitly document as unsupported.

## 2. `iter_source_files` doesn't filter symlinks
**Files:** `source_file_scanner.py` vs. `repository_cloner.py`

The cloner filters symlinks when computing repo size (security threat model: malicious repo symlinking to `/etc/passwd`). `iter_source_files` does not apply the same filter — `os.walk`'s `followlinks=False` stops descending into symlinked directories, but symlinked **files** with matching extensions are yielded and read.

**Action needed:** add `is_symlink()` check to `iter_source_files` or centralize in a shared helper.

## 3. Limited file-extension coverage per language
**File:** `source_parser.py`

Each language registers exactly one extension:
- Python: `.py` only (no `.pyi` stubs)
- Go: `.go` only (no `_test.go` special-casing)
- JavaScript: `.js` only (no `.jsx`, `.mjs`, `.cjs`)
- TypeScript: `.ts` only (no `.tsx`)

**Action needed:** decide if multi-extension support is in scope; would need `LanguageConfig` to support multiple extensions or separate grammars (e.g. tree-sitter-tsx for `.tsx`).

## 4. Repository size limit enforced after full clone
**File:** `repository_cloner.py`

`git clone` runs to completion before size check walks the checkout. For pathologically large repos, the full clone (disk I/O, bandwidth, time) already happened before rejection.

**Action needed:** confirm `GIT_CLONE_FLAGS` includes shallow-clone protections; if not, consider pre-clone size check via `git ls-remote`/API metadata.

## 5. `full_name` docstring invariant doesn't universally hold
**File:** `code_chunk.py`

Docstring states: "when defined_in_class is set, full_name == f'{defined_in_class}.{name}'". But `build_definition_chunk` computes `full_name` from `namespace` first, which can produce a longer dotted path when nested inside both a class and a function.

**Action needed:** fix docstring to reflect actual namespace-aware rule.

## 6. `CodeChunk.docstring` field entirely unpopulated
**File:** `code_chunk.py`

Field exists and is documented as "Reserved for later; always None for now." Nothing populates it.

**Action needed:** implement docstring extraction or remove the field.
