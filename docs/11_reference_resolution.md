# Step 11 — Cross-Repository Reference Resolution

**Module:** `app/ingestion/refs/resolver.py`
**Entry point:** `resolve_all_chunk_references(all_parsed_chunks: list[ParsedFileChunks])`

## Purpose
Once every file is chunked (Steps 1–10), turn each chunk's raw `RefRecord.text` into concrete `points_to` chunk IDs using indexes built from the **whole** repository.

## Indexes built once, up front
- `build_definition_index` — global `name/full_name -> [chunk_id, ...]` for all `RESOLVABLE_KINDS` chunks.
- `build_file_symbol_index` — same, bucketed per `file_path`.
- `build_dir_symbol_index` — same, bucketed per directory (for Go package-directory imports).
- `build_inheritance_graph` — `class_chunk_id -> [parent_chunk_id, ...]` from `CLASS_SKELETON` chunks' `INHERITANCE` references.

`RESOLVABLE_KINDS = (DEFINITION, MERGED_GROUP, CLASS_SKELETON, FUNCTION_SKELETON)` — these chunks get their references resolved.

## Resolution order, per reference (`resolve_chunk_references`)
Tried in this exact order, first hit wins:

### 1. Self reference (`_resolve_self_reference`)
For `self.`/`cls.`/`this.`-prefixed text, only if chunk has `defined_in_class`:
- Looks up `{class}.{rest}` in current file first, falls back to global index.
- If not found, walks inheritance graph BFS (with cycle protection) checking each ancestor class's file for `{ancestor}.{rest}`.

**Example:**
```python
class Base:
    def helper(self): pass

class Child(Base):
    def method(self):
        self.helper()  # → resolves to Base.helper via inheritance walk
```

### 2. Same-file reference (`_resolve_same_file_reference`)
Plain unqualified name lookup within the chunk's own file.

**Example:**
```python
def local_helper(): pass

def main():
    local_helper()  # → resolves to same-file local_helper
```

### 3. Import reference (`_resolve_import_reference`)
Splits `text` on first `.` into `root` + `rest`, looks up `root` in `import_bindings`:
- `MODULE` kind: target is `rest` inside resolved file (e.g. `os.path.join` → `path.join` inside `os`).
- `NAMED` kind: bound name itself is the target, rest is attribute access.

Tries resolved path as file first, then as directory (Go).

**Example:**
```python
from app.utils import helper

def main():
    helper()  # → resolves to app/utils.py's helper function
```

### 4. Global fallback (`_resolve_global_reference`)
Lookup across entire repository-wide index.

## Same-file before import: why?
Local definitions shadow imports. Given:
```python
from app.utils import helper  # imported helper

def helper():                  # local helper (shadows import)
    pass

def main():
    helper()  # resolves to LOCAL helper, not imported one
```
Resolution order ensures correct scoping semantics.

## Cross-language guard
If a reference resolves to a chunk with a different `language`, the match is discarded (`points_to = None`).

## Status assignment
- `LOCAL` — resolved to a chunk in this repo.
- `EXTERNAL` — root name is a resolved import binding whose target path is `None` (third-party/stdlib).
- `BUILTIN` — root name is in the language's `BUILTINS` set.
- `UNRESOLVED` — none of the above.

## Output
No return value — `resolve_chunk_references` mutates each `RefRecord.points_to`/`.status` **in place**.
