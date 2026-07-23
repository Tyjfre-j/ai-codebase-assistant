# Step 6 — Building CodeChunk Objects

**Module:** `app/ingestion/chunking/chunk_factory.py`

Three builder functions turn classified nodes into concrete `CodeChunk` records. All compute `chunk_id` via `stable_chunk_id(file_path, start_byte, full_name)` — a truncated SHA1, deterministic across re-runs.

## `build_definition_chunk(node, file_path, parsed, captures, definition_ids, parent_chunk_id)`
For a `DEFINITION`-kind node:
- Resolves `defined_in_class` via `get_enclosing_class_name`.
- Resolves `name` via `get_definition_name`.
- Builds `full_name`: prefers dotted `namespace` path, falls back to `"{class}.{name}"`, then bare `name`.
- Stores full source text as `code`.
- Extracts call/inheritance references via `extract_reference_records(node, content, ref_query, definition_ids)` — scoped to just this node's subtree.
- `parent_chunk_id` links to enclosing `FILE_SKELETON` or `DEFINITION_SKELETON`.

## `build_skeleton_chunk(node, file_path, parsed, captures, definition_ids, parent_chunk_id)`
Builds a synthetic stub for an oversized definition that has nested definitions inside it (to prevent double-counting code):
- Keeps everything from the definition start up to (but not including) its body, appends `"..."`.
- Handles `decorated_definition` wrapper to pull out the actual definition body correctly.
- `end_byte = node.start_byte` (synthetic zero-width slice).
- No references extracted (the elided body has nothing to extract).

### Example skeleton output
```python
def big_function(a, b):
    ...
```

## `build_file_skeleton_chunk(root_node, file_path, parsed, definition_ids, import_ids)`
Builds a synthetic summary chunk for an entire file when the file size exceeds the `skeleton_threshold`:
- Scans all top-level children of the file's root node.
- Retains docstrings, top-level constants, and other module-level code exactly as written.
- Replaces oversized class/function definitions with compact stub signatures.
- Replaces import blocks with a `"# imports elided"` placeholder.
- `end_byte = start_byte` (synthetic zero-width slice).
- Extracts references from the retained module-level code (which allows tracking globals used in top-level setup).

## Output
Fully-formed `CodeChunk` instances with `references[*].points_to = None` (resolution happens later in the pipeline).
