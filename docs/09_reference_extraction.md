# Step 9 — Extracting Raw References

**Module:** `app/ingestion/refs/extractor.py`
**Entry point:** `extract_reference_records(node, content, ref_query) -> list[RefRecord]`

## Purpose
Given one chunk's own AST subtree, find every call and inheritance
reference inside it and produce **unresolved** `RefRecord`s (text only —
`points_to` stays `None` until Step 11).

## What it captures (via the language's `REF_QUERY`)
- **Bare calls** — `reference.call` (e.g. `get_user()` → text `"get_user"`).
- **Attribute/method calls** — paired `reference.call.object` +
  `reference.call.attr` captures. These are matched up by their *shared
  parent node* (both captures' parent must be the same call/member-access
  node, keyed by `(start_byte, end_byte)`), then rendered as
  `"{object_text}.{attr_text}"` (e.g. `"self.get_user"`).
- **Base classes** — `reference.base_class` (e.g. `Base` in
  `class Child(Base):`), recorded with `RefKind.INHERITANCE`.

## Output
`list[RefRecord]`, each with `text`, `kind` (`CALL` or `INHERITANCE`),
`points_to=None`, and `status=RefStatus.UNRESOLVED` (the dataclass default).
This is attached to `CodeChunk.references` at construction time in Step 6;
resolution against the rest of the repository happens later in Step 11.
