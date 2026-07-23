# Step 5 — Classifying the AST into Chunk Candidates

**Module:** `app/ingestion/chunking/chunk_candidates.py`
**Entry point:** `walk_top_level(root, definition_ids, budget, file_path)`

## Purpose
Walk the parse tree once and label definition nodes as one of two candidate kinds, without yet building `CodeChunk` objects: `DEFINITION` or `DEFINITION_SKELETON`. Non-definition code is no longer chunked directly; instead, large files produce a full `FILE_SKELETON` in step 6.

## Core recursive logic (`_walk`)
For a given node:

### 1. It's a captured definition (`node.id in definition_ids`)

- If size ≤ budget → `DEFINITION` (whole definition, no recursion)
- If size > budget AND has nested definitions → `DEFINITION_SKELETON` + recurse into children
- If size > budget AND no nested definitions → `DEFINITION` (keep whole despite oversized)

### 2. Not a definition, but contains one
→ recurse into children without emitting anything for this node.

## Output
`list[tuple[kind, list[Node], enclosing_def_node]]` in document order — flat list of candidates ready for chunk building.

## Examples

### Example 1: Small class (fits budget)
```python
class Tiny:
    def __init__(self): pass
```
Budget = 2000, class size = 50.

Candidates:
```
[(DEFINITION, [Tiny_node], None)]
```
Result: One `DEFINITION` chunk containing the whole class.

### Example 2: Oversized class with methods
```python
class MyClass:
    """Docstring."""
    CLASS_VAR = 42

    def method_a(self):
        pass

    def method_b(self):
        pass
```
Budget = 200, class size = 500.

Candidates:
```
[(DEFINITION_SKELETON, [MyClass_node], None),
 (DEFINITION, [method_a_node], MyClass_node),
 (DEFINITION, [method_b_node], MyClass_node)]
```

### Example 3: Nested oversized classes
```python
class Outer:
    class Inner:
        def inner_method(self): pass

    def outer_method(self): pass
```
Budget = 100, both classes oversized.

Candidates:
```
[(DEFINITION_SKELETON, [Outer_node], None),
 (DEFINITION_SKELETON, [Inner_node], Outer_node),
 (DEFINITION, [inner_method_node], Inner_node),
 (DEFINITION, [outer_method_node], Outer_node)]
```
