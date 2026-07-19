# Step 4 — Running Queries & Normalizing Captures

**Module:** `app/ingestion/chunking/query_captures.py`
**Entry point:** `run_captures(parsed: ParsedFile) -> dict[str, list[Node]]`

## Purpose
Run the language's compiled `QUERY` against the whole file's parse tree exactly once, and hand back a clean `capture_name -> [Node, ...]` dict that every later stage reuses.

## What it does
1. Verifies the file's language has a `LANG_HELPERS` entry, raising `UnregisteredLanguageError` otherwise.
2. Executes the query via `QueryCursor.captures(...)`, normalizing both old-style `list[(Node, capture_name)]` and new-style `dict[capture_name, list[Node]]` into the same `captures_by_name` dict.
3. **Decorator unwrapping** — for every capture in `DEF_CAPTURES`, each node is passed through `unwrap_decorated_definition_node(node)`. For Python this promotes a bare `function_definition`/`class_definition` up to its enclosing `decorated_definition` node so decorators aren't dropped. Go/JS/TS return unchanged.
4. **De-duplication by logical span** — key is `(start_byte, end_byte, node.type)`, not `node.id`, since tree-sitter can return separate `Node` wrappers for the same underlying span.

## Output
`dict[str, list[Node]]` keyed by capture name (`func.def`, `class.def`, `import.stmt`, `import.module`, etc.), deduplicated for definition captures. This `captures` dict is threaded through `chunk_file`, `group_leftovers`, and `extract_import_bindings_for_file`.
