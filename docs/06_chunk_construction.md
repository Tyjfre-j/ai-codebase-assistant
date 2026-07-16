# Step 6 — Building CodeChunk Objects

**Module:** `app/ingestion/chunking/chunk_factory.py`

Four builder functions turn classified nodes (Step 5) into concrete
`CodeChunk` records. All four compute `chunk_id` via
`stable_chunk_id(file_path, start_byte, full_name)` — a truncated SHA1 of
`"{file_path}:{start_byte}:{full_name}"`, deterministic across re-runs unless
the chunk moves or is renamed.

## `build_definition_chunk(node, file_path, parsed, captures)`
For a `DEFINITION`-kind node (function, method, or an under-budget class):
- Resolves `defined_in_class` via `get_enclosing_class_name`.
- Resolves `name` via `get_definition_name`.
- Builds `full_name`: prefers a full dotted `namespace` path
  (`get_namespace`, when the language supports it) over the simpler
  `"{class}.{name}"` fallback, over the bare `name`.
- Stores the full source text (`node_text`) as `code`.
- Extracts call/inheritance references from *this node's own subtree* via
  `extract_reference_records` (Step 9) — so a definition's references are
  scoped to just its own body, not the whole file.

## `build_leftover_code_chunk(segments, file_path, parsed)`
Takes one or more contiguous node segments (already split at import
boundaries by Step 7) and joins them with plain `"\n"`. Each segment's own
byte range is sliced directly from source, preserving exact original
formatting *within* a segment — but text that originally sat *between*
segments (e.g. an import line that was filtered out) is deliberately
dropped, not reproduced.

## `build_class_skeleton_chunk(class_node, file_path, parsed)`
Builds a compact synthetic "stub" instead of the full class body:
- Header/footer via `get_class_skeleton_header`/`get_class_skeleton_footer`
  (falls back to a bare `f"class {name}:"` header with no footer if the
  language doesn't define these).
- One line per member via `get_class_member_stub_info` (per-language: method
  name + params + decorators + async/def-keyword prefix), rendered as
  `"    {decorators}{prefix} {name}{params}: ..."`. If a language doesn't
  implement member-stub extraction, or the class has no members, the body
  falls back to a single `"    ..."` line.
- `end_byte` is deliberately set equal to `start_byte` (see `CodeChunk`'s own
  docstring: "same as start_byte for empty skeleton chunks") since the
  `code` field is synthetic, not a real source slice.
- `references` are filtered to `RefKind.INHERITANCE` only, extracted from
  the *whole* class node's subtree — this is what later powers the
  inheritance graph in Step 11.
- Raises `ChunkExtractionError` (wrapping the original exception, with the
  class name and node type) if a member-stub extraction call throws.

## `build_function_skeleton_chunk(func_node, file_path, parsed, captures)`
Used when a definition is oversized but has a nested definition worth
preserving. Keeps everything from the function's start up to (but not
including) its body, appends a literal `"..."`, and — like the class
skeleton — sets `end_byte = func_node.start_byte`. Does **not** extract any
references (an elided body has nothing to extract calls from).

## Output
Fully-formed `CodeChunk` instances, one per candidate, still un-merged and
with `references[*].points_to` still `None` (resolution happens later, in
Step 11, after every file in the repo has been chunked).
