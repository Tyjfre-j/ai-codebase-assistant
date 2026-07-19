# Step 9 — Extracting Raw References

**Module:** `app/ingestion/refs/extractor.py`
**Entry point:** `extract_reference_records(node, content, ref_query, definition_ids=None) -> list[RefRecord]`

## Purpose
Given one chunk's own AST subtree, find every call and inheritance reference and produce **unresolved** `RefRecord`s (`points_to = None` until Step 11).

## What it captures (via the language's `REF_QUERY`)

### Bare calls — `reference.call`
```python
get_user()  # → text "get_user"
```

### Attribute/method calls — paired `reference.call.object` + `reference.call.attr`
Matched by shared parent node (keyed by `(start_byte, end_byte)`):
```python
self.get_user()  # → text "self.get_user"
obj.helper()     # → text "obj.helper"
```

### Base classes — `reference.base_class`
```python
class Child(Base):  # → text "Base", kind=INHERITANCE
```

## Owner name resolution (`definition_ids`)
When `definition_ids` is provided, `_find_owner` walks up from the call node to find which direct definition (function/method) contains it. This populates `RefRecord.owner_name` — useful for whole-class/function chunks to know which inner method owns a reference.

## Output
`list[RefRecord]`, each with:
- `text` — as written at call site
- `kind` — `CALL` or `INHERITANCE`
- `points_to` — `None` (resolved in Step 11)
- `status` — `UNRESOLVED` (default)
- `owner_name` — containing method name (if `definition_ids` provided)

Attached to `CodeChunk.references` at construction time in Step 6.
