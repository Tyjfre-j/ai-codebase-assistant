# Reference Extraction & Resolution

Once source files are chunked, the pipeline extracts dependency references (e.g., function calls, attribute access, class inheritance) to build a semantic call graph.

## 1. Extraction
Tree-sitter queries (`REF_QUERY`) capture references directly from the AST. For example, in Python:
- `(call function: (identifier) @reference.call)` captures bare function calls.
- `(attribute object: (_) @reference.call.object attribute: (identifier) @reference.call.attr)` captures method and attribute access.

Each capture yields a `RefRecord` on the `CodeChunk`, initialized with an `UNRESOLVED` status. 

## 2. Multi-Pass Resolution
The `resolve_all_chunk_references` function in `resolver.py` coordinates a multi-pass resolution strategy to link references to their defining chunk. It iterates over all chunks and attempts to resolve each reference text against four progressive scopes:

1. **Self / Class Scope (`_resolve_self_reference`)**: 
   Resolves `self.method()` or `this.method()`. It looks up the current chunk's `defined_in_class`, checks the inheritance graph to gather all parent classes, and searches for the method name inside the local file's symbol index among those class scopes.
2. **Import Bindings (`_resolve_import_reference`)**: 
   Resolves imported symbols. The pipeline extracts import statements, maps bound aliases to their resolved target modules, and looks for the definition matching the imported name within the `file_symbol_index` or `dir_symbol_index` of the target module.
3. **Same-File Scope (`_resolve_same_file_reference`)**: 
   Fallback for local definitions within the same file that weren't imported but are globally accessible in the file's namespace.
4. **Global Scope (`_resolve_global_reference`)**: 
   Final fallback for globally unique definitions across the repository. If a symbol name exists in exactly one place in the global `symbol_index`, the reference is linked there.

## 3. Reference Statuses
When a reference is processed, its status is updated based on resolution success:
- `LOCAL`: Successfully resolved to a known `CodeChunk` in the repository.
- `EXTERNAL`: Resolved to an import that points to a third-party library or standard library not present in the local codebase (e.g., `import requests`). This is detected via `_is_external_import` which flags imports that lack a resolved local path.
- `BUILTIN`: Matched against a known list of language globals (e.g., `print`, `len` in Python, `console.log` in JS). Detected via the `is_builtin` helper on the language module.
- `UNRESOLVED`: Could not be resolved statically. This typically occurs with dynamically typed instance variables, dependency injection parameters, or built-in methods called on dynamic variables (like `"string".split()`).
