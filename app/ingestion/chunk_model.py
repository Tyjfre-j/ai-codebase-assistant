"""The CodeChunk model: a structured unit extracted from source code."""

from dataclasses import dataclass
from enum import Enum


class ChunkType(str, Enum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    IMPORT = "import"
    MODULE_LEVEL = "module_level"
    FILE_SUMMARY = "file_summary"


@dataclass(frozen=True)
class CodeChunk:
    chunk_id: str
    file_path: str
    language: str
    chunk_type: ChunkType
    qualified_name: str
    parameters: tuple[str, ...]
    parent_class: str | None
    imports: tuple[str, ...]
    source_code: str
    start_line: int
    end_line: int

    def __post_init__(self):
        if self.start_line > self.end_line:
            raise ValueError(
                f"start_line ({self.start_line}) > end_line ({self.end_line}) for {self.qualified_name}"
            )
        if not self.chunk_id:
            raise ValueError("chunk_id must not be empty")