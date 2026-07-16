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
- **Definitions**: Functions, classes, and interfaces are extracted as definition chunks. Small adjacent definitions are merged.
- **Leftovers**: Code outside of definitions (like global scripts or standalone module-level statements) is grouped into "leftover" chunks.
- **Class Skeletons**: Synthetic zero-width chunks are generated for class definitions. They contain method stubs, allowing the retriever to see the overall class structure without pulling in every method implementation.

Each definition chunk is assigned a stable ID (`stable_chunk_id`) for persistent indexing.
