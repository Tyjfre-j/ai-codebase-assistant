
from dataclasses import dataclass


@dataclass
class CodeChunk:
    """Serializable unit of code produced by the ingestion chunker."""
    # identity
    chunk_id: str
    qualified_name: str
    symbol_name: str
    parent_symbol: str | None

    # origin
    file_path: str
    start_byte: int
    end_byte: int
    language: str

    # content
    content: str
    docstring: str | None

    # classification
    node_type: str
    chunk_kind: str  # "definition" | "leftover" | "merged_group" | "class_skeleton"
    merged_symbols: list[str] | None

    # sizing
    size_chars: int

    # filled in later, by the reference-extraction pass, not by chunking
    refs: list[str] | None = None
