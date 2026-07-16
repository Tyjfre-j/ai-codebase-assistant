from dataclasses import dataclass, field


class ChunkKind:
    """The canonical set of values CodeChunk.kind can take."""

    DEFINITION = "definition"
    CLASS_SKELETON = "class_skeleton"
    FUNCTION_SKELETON = "function_skeleton"
    LEFTOVER = "leftover"
    MERGED_GROUP = "merged_group"

class RefKind:
    """The values RefRecord.kind can take."""

    CALL = "call"
    INHERITANCE = "inheritance"

class RefStatus:
    """The values RefRecord.status can take."""

    LOCAL = "local"
    EXTERNAL = "external"  # not yet implemented anywhere
    UNRESOLVED = "unresolved"

class ImportKind:
    """The values an import binding's kind can take."""

    MODULE = "module"  # e.g. `import os` -> "os" binds the whole module
    NAMED = "named"    # e.g. `from os import path` -> "path" binds one specific symbol

@dataclass
class RefRecord:
    """One reference (a call or an inheritance) found inside a chunk's code."""

    text: str  # What was literally written at the reference site, e.g. "get_user", "self.get_user", "Base".
    kind: str  # RefKind.CALL (this invokes something) or RefKind.INHERITANCE (this extends something).
    points_to: str | None  # The chunk_id this reference resolves to, once we know it; None until then.
    status: str = RefStatus.UNRESOLVED  # RefStatus.LOCAL, RefStatus.EXTERNAL (not yet implemented), or RefStatus.UNRESOLVED.

@dataclass
class CodeChunk:
    """One retrievable piece of a source file, usually a single function, method, or class."""

    chunk_id: str  # A stable id for this chunk, used to point at it from elsewhere.
    full_name: str  # The name including its class, e.g. "ShapeCalculator.circle_area".
    name: str  # Just this chunk's own name, e.g. "circle_area"; "<anonymous>" or "<leftover>" if unnamed.
    defined_in_class: str | None  # The class this lives inside, if any, e.g. "ShapeCalculator".
    # NOTE: when defined_in_class is set, full_name == f"{defined_in_class}.{name}"

    file_path: str  # Which file this chunk came from.
    start_byte: int  # Where this chunk starts in the source file.
    end_byte: int  # Where this chunk ends; same as start_byte for empty skeleton chunks.
    language: str  # "python", "go", "javascript", or "typescript".

    code: str  # The actual text of this chunk (or a synthetic stub for class skeletons).
    docstring: str | None  # Reserved for later; always None for now.

    node_type: str | None  # The tree-sitter node type this came from, e.g. "function_definition".
    kind: str  # ChunkKind.DEFINITION / CLASS_SKELETON / LEFTOVER / MERGED_GROUP -- what role this chunk plays.
    merged_names: list[str] | None  # The original names bundled in here, if kind is ChunkKind.MERGED_GROUP.

    size_chars: int  # How many characters of code this chunk holds.

    references: list[RefRecord] = field(default_factory=list)  # Filled in later, once refs are extracted.


@dataclass
class ParsedFileChunks:
    """Everything produced by chunking one file, plus its import info for later resolution."""

    file_path: str  # The file this came from.
    chunks: list[CodeChunk]  # Every chunk found in this file.
    import_text: str  # The raw text of this file's imports.
    import_ranges: list[tuple[int, int]]  # Where each import statement sits in the file.
    import_bindings: dict[str, tuple[str | None, str, str]] = field(default_factory=dict)
    # Maps each name used in the code to (the file it actually comes from, or None; its original name).

@dataclass
class SkippedFile:
    """One file that didn't make it into the chunk output, and why."""
    file_path: str
    reason: str  # "empty", "oversized", "binary", "minified", an OSError, or an exception class name.


@dataclass
class RepositoryChunkResult:
    """Everything `chunk_repository` produces: successful per-file results plus a skip summary."""
    files: list[ParsedFileChunks]
    skipped: list[SkippedFile]

    def skip_counts_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for skipped_file in self.skipped:
            counts[skipped_file.reason] = counts.get(skipped_file.reason, 0) + 1
        return counts