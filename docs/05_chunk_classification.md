# Step 5 — Classifying the AST into Chunk Candidates

**Module:** `app/ingestion/chunking/chunk_candidates.py`
**Entry point:** `walk_top_level(root, definition_ids, budget, class_node_types, file_path)`

## Purpose
Walk the parse tree once and label every node as one of four candidate kinds, without yet building `CodeChunk` objects: `DEFINITION`, `CLASS_SKELETON`, `FUNCTION_SKELETON`, or `LEFTOVER`.

## Core recursive logic (`_walk`)
For a given node:

### 1. It's a captured definition (`node.id in definition_ids`)

**Case A: Class node (`node.type in class_node_types`)**
- If size ≤ budget → `DEFINITION` (whole class, no recursion)
- If size > budget → `CLASS_SKELETON` + recurse into children with `absorb_leftovers=True`

**Case B: Function/method node**
- If size ≤ budget → `DEFINITION` (whole function, no recursion)
- If size > budget AND has nested definitions → `FUNCTION_SKELETON` + recurse with `absorb_leftovers=True`
- If size > budget AND no nested definitions → `DEFINITION` (keep whole despite oversized)

### 2. Not a definition, no descendant is one
→ `LEFTOVER` — the whole subtree is non-definition code.

### 3. Not a definition, but contains one
→ recurse into children without emitting anything for this node.

## Absorbing leftovers (`absorb_leftovers`)
When recursing into a `CLASS_SKELETON` or `FUNCTION_SKELETON`, `LEFTOVER` candidates are **skipped** instead of emitted. This means:
- Class-level variables, docstrings, and comments are absorbed into the class skeleton
- Function-level local variables and statements are absorbed into the function skeleton
- No meaningless orphaned leftover chunks are produced inside classes or functions

## Grouping leftovers (`_walk_children`)
Adjacent `LEFTOVER` results are buffered and merged into one emitted entry. Non-leftover kinds flush the buffer first, preserving document order.

## Output
`list[tuple[kind, nodes, enclosing_def_node, scope_id]]` in document order — flat list of candidates ready for chunk building.

## Examples

### Example 1: Small class (fits budget)
```python
class Tiny:
    def __init__(self): pass
```
Budget = 2000, class size = 50.

Candidates:
```
[(DEFINITION, [Tiny_node], None, None)]
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
[(CLASS_SKELETON, [MyClass_node], None, None),
 (DEFINITION, [method_a_node], MyClass_node, None),
 (DEFINITION, [method_b_node], MyClass_node, None)]
```
Note: `CLASS_VAR` and docstring are absorbed — no `LEFTOVER` chunks.

### Example 3: Oversized function with nested functions
```python
def big_function():
    x = 1

    def nested_a():
        pass

    def nested_b():
        pass
```
Budget = 200, function size = 500.

Candidates:
```
[(FUNCTION_SKELETON, [big_function_node], None, None),
 (DEFINITION, [nested_a_node], big_function_node, None),
 (DEFINITION, [nested_b_node], big_function_node, None)]
```
Note: `x = 1` is absorbed — no `LEFTOVER` chunk.

### Example 4: Top-level leftovers
```python
MODULE_VAR = 42

def func(): pass

HELPER = "x"
```

Candidates:
```
[(LEFTOVER, [MODULE_VAR_node], None, None),
 (DEFINITION, [func_node], None, None),
 (LEFTOVER, [HELPER_node], None, None)]
```

### Example 5: Nested oversized classes
```python
class Outer:
    class Inner:
        def inner_method(self): pass

    def outer_method(self): pass
```
Budget = 100, both classes oversized.

Candidates:
```
[(CLASS_SKELETON, [Outer_node], None, None),
 (CLASS_SKELETON, [Inner_node], Outer_node, None),
 (DEFINITION, [inner_method_node], Inner_node, None),
 (DEFINITION, [outer_method_node], Outer_node, None)]
```
