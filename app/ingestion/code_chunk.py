
from dataclasses import dataclass


@dataclass
class CodeChunk:
    """Serializable retrievable piece of a source file."""

    chunk_id: str  # Stable id used to reference this chunk across indexing runs.
    qualified_name: str  # Full symbol path, or a synthetic path for leftover chunks.
    symbol_name: str  # Bare identifier, "<anonymous>" when unnamed, or "<leftover>".
    parent_symbol: str | None  # Enclosing class/struct name when one is resolved.

    file_path: str  # Source file this chunk was extracted from.
    start_byte: int  # Start byte in the original source
    end_byte: int  # End byte in the original source; zero-width for skeletons.
    language: str  # Parsed language name, such as "python", "go", "javascript", or "typescript".

    content: str  # Source text or synthetic class skeleton text embedded for retrieval.
    docstring: str | None  # Reserved for future docstring extraction; currently None.

    node_type: str | None  # Tree-sitter node type, such as "function_definition".
    chunk_kind: str  # One of "definition", "leftover", "merged_group", or "class_skeleton".
    merged_symbols: list[str] | None  # Original symbol names when chunk_kind is "merged_group".

    size_chars: int  # Character length of content, used by chunk splitting and merging.

    refs: list[str] | None = None  # Filled later by reference extraction, not chunking.
