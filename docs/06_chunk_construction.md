# Step 6 — Building CodeChunk Objects

**Module:** `app/ingestion/chunking/chunk_factory.py`

Four builder functions turn classified nodes into concrete `CodeChunk` records. All compute `chunk_id` via `stable_chunk_id(file_path, start_byte, full_name)` — a truncated SHA1, deterministic across re-runs.

## `build_definition_chunk(node, file_path, parsed, captures, definition_ids, parent_chunk_id)`
For a `DEFINITION`-kind node (function, method, or under-budget class):
- Resolves `defined_in_class` via `get_enclosing_class_name`.
- Resolves `name` via `get_definition_name`.
- Builds `full_name`: prefers dotted `namespace` path, falls back to `"{class}.{name}"`, then bare `name`.
- Stores full source text as `code`.
- Extracts call/inheritance references via `extract_reference_records(node, content, ref_query, definition_ids)` — scoped to just this node's subtree.
- `parent_chunk_id` links to enclosing `CLASS_SKELETON` or `FUNCTION_SKELETON` if this definition is nested inside one.

## `build_leftover_code_chunk(segments, file_path, parsed, parent_chunk_id)`
Takes one or more contiguous node segments and joins them with `"\n"`. Each segment's byte range is sliced directly from source, preserving original formatting within the segment. Text between segments (e.g. import lines) is deliberately dropped.

## `build_file_overview_chunk(root, file_path, parsed, top_level_names, import_text)`
Builds a synthetic metadata chunk:
- `# file: {file_path}`
- Module docstring (if any)
- `# imports:` + import text
- `# defines:` + top-level name list

`kind = FILE_OVERVIEW`, `parent_chunk_id = None`.

## `build_class_skeleton_chunk(class_node, file_path, parsed, captures, parent_chunk_id)`
Builds a compact synthetic stub for an oversized class:
- Header/footer via `get_class_skeleton_header`/`get_class_skeleton_footer` (falls back to `f"class {name}:"`).
- **All body children rendered**: class-level code (docstrings, variables) as-is, method signatures as stubs via `get_class_member_stub_info`.
- If no members: falls back to `"    ..."`.
- `end_byte = start_byte` (synthetic chunk, not a real source slice).
- `references` filtered to `INHERITANCE` only — powers the inheritance graph in Step 11.
- Raises `ChunkExtractionError` if member-stub extraction fails.

### Example class skeleton output
```python
class MyClass:
    """Docstring."""
    CLASS_VAR = 42
    def method_a(self): ...
    def method_b(self): ...
```

## `build_function_skeleton_chunk(func_node, file_path, parsed, captures, parent_chunk_id)`
For an oversized function with nested definitions:
- Keeps everything from function start up to (but not including) its body, appends `"..."`.
- Handles `decorated_definition` wrapper: looks up `body` on the inner `function_definition`.
- `end_byte = func_node.start_byte` (synthetic).
- No references extracted (elided body has nothing to extract).

### Example function skeleton output
```python
def big_function(a, b):
    ...
```

## Output
Fully-formed `CodeChunk` instances with `references[*].points_to = None` (resolution happens in Step 11).
