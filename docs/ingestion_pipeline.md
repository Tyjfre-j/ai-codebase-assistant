# Ingestion Pipeline

The ingestion pipeline is responsible for crawling a target repository, identifying source files, parsing them via Tree-sitter, and splitting them into meaningful chunks for downstream LLM retrieval.

## 1. Repository Cloning & Scanning
The pipeline starts with `RepositoryCloner`, which safely clones a target git repository into a temporary directory, respecting timeouts and size limits. `source_file_scanner` then walks the repository, collecting source files that match our supported file extensions while respecting `.gitignore`, `node_modules`, and standard exclusion rules.

## 2. Validation
`source_file_validation` filters the scanned files to reject:
- Empty files
- Files exceeding size or line limits
- Auto-generated or minified files

## 3. Parsing & Chunking
Valid files are passed to `CodeParser` which loads the correct Tree-sitter grammar based on the language. The parsed syntax tree is handed to `chunk_file()` in `chunk_pipeline.py`.

### Walk Top Level & Chunk Candidates
`walk_top_level()` explores the syntax tree starting from the root node. It identifies **definition candidates** (using capture IDs from the tree-sitter query) and separates them from non-definition nodes.
- When it encounters a class definition, it emits a `CLASS_SKELETON` candidate, and then continues walking *inside* the class body to extract its individual methods as distinct definition candidates.
- If a definition exceeds the chunk budget, `walk_top_level()` falls back to walking *inside* the definition, extracting nested classes/functions or producing a `FUNCTION_SKELETON`.

### Chunk Building
- **Definitions**: Functions, classes, and interfaces are extracted as `ChunkKind.DEFINITION`. `build_definition_chunk` extracts references and assigns a stable ID (`stable_chunk_id`) for persistent indexing.
- **Leftovers**: Code outside of definitions (like global scripts, imports, or standalone module-level statements) is grouped into "leftover" chunks by `group_leftovers()`. Imports are also stripped out and stored separately (`import_text`, `import_ranges`).
- **Class Skeletons**: Synthetic zero-width chunks (`ChunkKind.CLASS_SKELETON`) are generated for class definitions. They contain method stubs (name, decorators, parameters), allowing the retriever to see the overall class structure without pulling in every method implementation.

### Output
`chunk_file()` returns a tuple containing:
1. `CodeChunk` objects representing the extracted codebase segments.
2. `import_text`: The concatenated text of all import statements in the file.
3. `import_ranges`: The byte ranges of those imports in the original source file.
4. `captures`: The raw tree-sitter captures to be reused in the import-binding extraction phase.
