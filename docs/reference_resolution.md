# Reference Extraction & Resolution

Once source files are chunked, the pipeline extracts dependency references (e.g., function calls, attribute access, class inheritance) to build a semantic call graph.

## 1. Extraction
Tree-sitter queries (`REF_QUERY`) capture references directly from the AST. Each capture yields a `RefRecord` on the `CodeChunk`, initialized with an `UNRESOLVED` status. 

## 2. Multi-Pass Resolution
The `resolve_all_chunk_references` function coordinates a multi-pass resolution strategy to link references to their defining chunk:
1. **Self / Class Scope**: Resolves `self.method()` or `this.method()` by looking up the inheritance graph.
2. **Import Bindings**: Resolves imported symbols. The pipeline extracts import statements, resolves them to specific files/modules, and looks for definitions matching the imported name.
3. **Same-File Scope**: Fallback for local definitions within the same file that weren't imported.
4. **Global Scope**: Final fallback for globally available definitions across the repository.

## 3. Reference Statuses
When a reference is processed, its status is updated:
- `LOCAL`: Successfully resolved to a known `CodeChunk` in the repository.
- `EXTERNAL`: Resolved to an import that points to a third-party library or standard library not present in the local codebase (e.g., `import requests`).
- `BUILTIN`: Matched against a known list of language globals (e.g., `print` in Python, `console.log` in JS).
- `UNRESOLVED`: Could not be resolved statically (often occurs with dynamically typed instance variables or dependency injection parameters).
