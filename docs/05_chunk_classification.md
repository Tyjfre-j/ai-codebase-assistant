# Step 5 — Classifying the AST into Chunk Candidates

**Module:** `app/ingestion/chunking/chunk_candidates.py`
**Entry point:** `walk_top_level(root, definition_ids, budget, class_node_types)`

## Purpose
Walk the whole parse tree once and label every node as one of four
candidate kinds, without yet building any `CodeChunk` objects:
`DEFINITION`, `CLASS_SKELETON`, `FUNCTION_SKELETON`, or `LEFTOVER`.

## Core recursive logic (`_walk`)
For a given node:
1. **It's a captured definition** (`node.id in definition_ids`):
   - If its type is in `class_node_types` → emit `CLASS_SKELETON` for this
     node, then still recurse into its children (`_walk_children`) so
     methods inside the class get their own definition chunks.
   - Else if its full size (`end_byte - start_byte`) fits the `budget` →
     emit a plain `DEFINITION` chunk for the whole subtree, no recursion.
   - Else if it contains a nested definition (e.g. a nested function) →
     emit `FUNCTION_SKELETON` (signature-only) for this node, then recurse
     into its children to chunk the nested definition(s) separately.
   - Else (oversized, nothing nested to split around) → still emit a full
     `DEFINITION` chunk rather than downgrading it to an anonymous
     leftover, on the principle that keeping its name/kind/parent is more
     valuable than enforcing the budget.
2. **Not a definition, but no descendant is one either**
     (`_contains_definition` is false) → the whole subtree is `LEFTOVER`
     (module-level statements, comments, blank regions, etc.) — recursion
     stops here; the subtree isn't walked node-by-node.
3. **Not a definition, but something inside it is** → recurse into children
   without emitting anything for this node itself.

## Memoized containment check (`_contains_definition`)
A `dict[int, bool]` keyed by `node.id`, shared across the *entire* single
`walk_top_level` call. Without it, checking "does this subtree contain a
definition" from every ancestor on the way down would re-walk the same
subtree once per ancestor — quadratic in deeply nested oversized files.

## Grouping leftovers (`_walk_children`)
Iterates a node's children in document order, classifying each via `_walk`.
Adjacent `LEFTOVER` results are buffered and merged into one emitted
`LEFTOVER` entry (so leftover code doesn't fragment into one tiny chunk per
AST sibling); any non-leftover kind flushes the buffer first, preserving
overall document order in the returned list.

## Output
`list[tuple[chunk_kind: str, nodes: list[Node]]]` in document order — a flat
list of "candidates" ready to be turned into actual chunks (Step 6) or
grouped further (Step 7, for leftovers).
