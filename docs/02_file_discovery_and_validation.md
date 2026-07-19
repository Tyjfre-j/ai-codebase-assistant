# Step 2 — Source File Discovery & Validation

**Modules:** `app/ingestion/source_file_scanner.py`, `app/ingestion/source_file_validation.py`

## 2a. Discovery — `iter_source_files(root, extensions)`
Walks `root` with `os.walk`, pruning:
- any directory name in `_SKIP_DIRS` (e.g. `node_modules`, `.git`, build/dependency folders),
- any directory starting with `.`.

Yields every file whose suffix (`Path(filename).suffix`) is in the caller-supplied `extensions` set (built from the parser's registered `FILE_EXTENSION`s: `.py`, `.go`, `.js`, `.ts`).

## 2b. Path-based validation — `validate_file_thru_path(file_path, max_size_mb)`
Runs before the file is opened:
- `is_file_empty` — `os.path.getsize(...) == 0`
- `is_file_oversized` — size exceeds `max_size_mb * BYTES_PER_MB`

Both raise `FileAccessError` on `OSError`.

## 2c. Content-based validation — `validate_file_thru_content(file_path, content)`
Runs once bytes are read:
- `is_file_binary` — samples first 1024 bytes; any NUL byte or byte outside text set marks it binary.
- `is_file_minified` — three-tier heuristic over 8192-byte sample:
  - filename ending in `.min` is always minified;
  - single-line sample > 200 chars → minified;
  - < 10 lines: minified if every line is long (>200 chars);
  - 10+ lines: minified if ≥70% of lines are long AND average line length > 200.

Both return `ValidationResult(is_valid, reason)` using `InvalidFileReason` enum (`empty`, `oversized`, `binary`, `minified`).

## Output
A stream of `(file_path, content)` values that passed both validation layers.
