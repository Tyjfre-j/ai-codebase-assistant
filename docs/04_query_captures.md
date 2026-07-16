# Step 4 — Running Queries & Normalizing Captures

**Module:** `app/ingestion/chunking/query_captures.py`
**Entry point:** `run_captures(parsed: ParsedFile) -> dict[str, list[Node]]`

## Purpose
Run the language's compiled `QUERY` against the whole file's parse tree
exactly once, and hand back a clean `capture_name -> [Node, ...]` dict that
every later stage (chunk classification, import extraction) reuses instead
of re-querying the tree.

## What it does
1. Verifies the file's language has a `LANG_HELPERS` entry, raising
   `UnregisteredLanguageError` otherwise (defensive — should be unreachable
   given the registry check in Step 3, but guards against drift between the
   two registries).
2. Executes the query via tree-sitter's `QueryCursor.captures(...)`, which
   can return either an old-style `list[(Node, capture_name)]` or a
   newer `dict[capture_name, list[Node]]` depending on the tree-sitter
   binding version — both shapes are normalized into the same
   `captures_by_name` dict.
3. **Decorator unwrapping** — for every capture name in `DEF_CAPTURES`
   (`func.def`, `class.def`, `interface.def`), each captured node is passed
   through `language_helpers.unwrap_decorated_definition_node(node)`. For
   Python this promotes a bare `function_definition`/`class_definition` up
   to its enclosing `decorated_definition` node when one exists, so
   decorators aren't silently dropped from the chunk's code. Go/JS/TS have
   no such wrapper and return the node unchanged.
4. **De-duplication by logical span**, not `node.id` — two different query
   patterns can each match and independently unwrap to *distinct* `Node`
   objects that still denote the exact same source definition (this happens
   because tree-sitter can hand back separate `Node` wrapper objects for the
   same underlying span depending on which pattern matched). Dedup key is
   `(start_byte, end_byte, node.type)`.

## Output
`dict[str, list[Node]]` keyed by capture name (`func.def`, `func.name`,
`class.def`, `import.stmt`, `import.module`, etc.), deduplicated for the
three definition-capture names. This is the `captures` dict threaded through
`chunk_file`, `group_leftovers`, and `extract_import_bindings_for_file`.
