# Step 2 — Source File Discovery & Validation

**Modules:** `app/ingestion/source_file_scanner.py`,
`app/ingestion/source_file_validation.py`

## 2a. Discovery — `iter_source_files(root, extensions)`
Walks `root` with `os.walk`, pruning:
- any directory name in `_SKIP_DIRS` (e.g. the usual `node_modules`,
  `.git`-style build/dependency folders — exact contents live in
  `app/core/constants.py`, not included in this dump),
- any directory starting with `.`.

Yields every file whose suffix (`Path(filename).suffix`) is in the
caller-supplied `extensions` set (built from the parser's registered
`FILE_EXTENSION`s: `.py`, `.go`, `.js`, `.ts`).

Note: `os.walk`'s default `followlinks=False` means it won't *descend into*
symlinked directories, but it does not filter out symlinked **files** that
happen to match a tracked extension — those are yielded as-is. See the gaps
document for why this matters given the cloner explicitly guards against
symlinks elsewhere.

## 2b. Path-based validation — `validate_file_thru_path(file_path, max_size_mb)`
Runs before the file is even opened for content-based checks:
- `is_file_empty` — `os.path.getsize(...) == 0`
- `is_file_oversized` — size exceeds `max_size_mb * BYTES_PER_MB`

Both raise `FileAccessError` on `OSError` (e.g. race where the file
disappears between listing and stat).

## 2c. Content-based validation — `validate_file_thru_content(file_path, content)`
Runs once the bytes have already been read:
- `is_file_binary` — samples the first 1024 bytes; any NUL byte or any byte
  outside the "text" set (tabs/newlines/CR/FF/ESC + 0x20–0xFF) marks it
  binary.
- `is_file_minified` — three-tier heuristic over an 8192-byte sample:
  - filename ending in `.min` (e.g. `foo.min.js`) is always minified;
  - a single-line sample is minified if that line exceeds 200 chars;
  - fewer than 10 lines: minified only if *every* line is long;
  - 10+ lines: minified if ≥70% of lines are "long" (>200 chars) **and**
    the average line length exceeds 200 chars.

Both checks return a `ValidationResult(is_valid, reason)` using the
`InvalidFileReason` enum (`empty`, `oversized`, `binary`, `minified`), which
the orchestrator turns directly into a `SkippedFile` entry.

## Output
A stream of `(file_path)` values that passed both validation layers, each
paired with its already-read `content: bytes` by the caller
(`repo_chunker.chunk_repository`).
