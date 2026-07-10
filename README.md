# AI Codebase Assistant

AI Codebase Assistant is a work-in-progress backend for ingesting source code,
splitting it into retrievable chunks, and preparing those chunks for search,
embedding, and question-answering workflows.

The current implementation focuses on the ingestion layer: cloning repositories,
finding source files, validating file content, parsing supported languages with
Tree-sitter, and producing structured `CodeChunk` objects.

## Supported Languages

- Python
- Go
- JavaScript
- TypeScript

Language support lives in `app/ingestion/languages/`. Each language module
provides a Tree-sitter query plus small helper functions for resolving parent
symbols and class/member information.

## Project Layout

```text
app/
  core/
    exceptions.py                 Shared ingestion exception types.
  ingestion/
    repository_cloner.py          Secure repository cloning helpers.
    source_file_scanner.py        Finds source files under a repository.
    source_file_validation.py     Rejects empty, oversized, binary, or minified files.
    source_parser.py              Loads Tree-sitter parsers and parses files.
    source_text.py                Source slicing, symbol names, and stable ids.
    code_chunk.py                 Dataclass for retrievable source chunks.
    languages/                    Language queries and helper functions.
    chunking/
      chunk_pipeline.py           Main `chunk_file()` entry point.
      query_captures.py           Runs Tree-sitter queries and groups captures.
      chunk_candidates.py         Walks the syntax tree into chunk candidates.
      chunk_factory.py            Builds `CodeChunk` objects.
      definition_merger.py        Merges adjacent small definitions.
      leftover_chunks.py          Groups imports and non-definition code.
tests/
  fixtures/                       Sample files used by ingestion tests.
```

## Ingestion Flow

The intended flow is:

1. Clone a repository with `RepositoryCloner`.
2. Find supported source files with `iter_source_files`.
3. Validate each file by path and content.
4. Parse the file with `CodeParser`.
5. Chunk the parsed file with `chunk_file`.
6. Later pipeline stages can embed, store, and retrieve the resulting chunks.

The repo does not yet have one top-level orchestrator that wires every step
together into a single command.

## Chunking Overview

`chunk_file()` returns:

```python
chunks, import_text, import_ranges = chunk_file(file_path, parsed_file)
```

- `chunks`: `CodeChunk` objects for definitions, class skeletons, merged
  definition groups, and leftover source code.
- `import_text`: import statements concatenated separately from chunks.
- `import_ranges`: byte ranges for imports in the original source file.

Tree-sitter captures can overlap. For example, a Python class capture spans the
whole class while method captures inside it also appear separately. The chunking
walker handles this by emitting a synthetic class skeleton and then recursing
into the class body so methods can still become their own chunks.

Class skeleton chunks are synthetic and zero-width:

- `start_byte == end_byte`
- `chunk_kind == "class_skeleton"`
- `content` contains compact method stubs when member extraction is available,
  or `...` when no member stubs are found.

Definition chunks use stable ids:

```text
stable_chunk_id(file_path, start_byte, qualified_name)
```

That keeps a chunk identifiable across reruns unless it moves or is renamed.
Body content changes can be detected separately by hashing `content` in a future
incremental indexing step.

## CodeChunk Fields

`CodeChunk` is the main data model emitted by chunking. Important fields:

- `chunk_id`: stable identifier for indexing and lookup.
- `qualified_name`: full symbol path, or synthetic leftover name.
- `symbol_name`: bare symbol name.
- `parent_symbol`: enclosing class or struct when resolved.
- `file_path`: source file path.
- `start_byte` / `end_byte`: source byte range.
- `language`: parsed language name.
- `content`: source text or synthetic skeleton text.
- `node_type`: Tree-sitter node type.
- `chunk_kind`: `definition`, `leftover`, `merged_group`, or `class_skeleton`.
- `merged_symbols`: original symbols included in a merged chunk.
- `refs`: reserved for later reference extraction.

## Correctness Checks

The ingestion tests include two useful invariants:

- Parent symbol resolution works across Python, Go, JavaScript, and TypeScript.
- Chunk ranges plus import ranges account for every non-whitespace byte in the
  original file exactly once. Class skeletons are excluded from this range check
  because they are synthetic zero-width chunks.

## Running Tests

This project uses `uv`.

```bash
uv run pytest tests/ -v
```

For the focused ingestion checks:

```bash
uv run pytest tests/test_cloner.py tests/test_resolve_parent_class.py tests/test_reconstruction.py
```

Lint the ingestion package with:

```bash
uv run ruff check app/ingestion
```

## Current Gaps

- No top-level ingest command/API yet wires clone, scan, validate, parse, chunk,
  embed, and store into one flow.
- `CodeChunk.refs` is not populated yet.
- Embedding generation and vector storage are not wired to chunking yet.
- Chunk output is returned as definitions first and leftovers second, not sorted
  globally by source order.
- `docstring` exists on `CodeChunk` but is currently always `None`.

## Next Steps

1. Add an orchestration layer for full repository ingestion.
2. Extract symbol references and populate `CodeChunk.refs`.
3. Generate embeddings for chunk content.
4. Store chunks and embeddings in Qdrant.
5. Add incremental re-indexing based on stable ids and content hashes.
6. Build retrieval and answering endpoints.
