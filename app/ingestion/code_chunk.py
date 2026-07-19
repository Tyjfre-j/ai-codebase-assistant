from dataclasses import dataclass, field


class ChunkKind:
    """The canonical set of values CodeChunk.kind can take."""

    DEFINITION = "definition" # A function or methods of class or interface
    CLASS_SKELETON = "class_skeleton" # A synthetic chunk representing a class's skeleton, with no code of its own.
    FUNCTION_SKELETON = "function_skeleton" # A synthetic chunk representing a function's skeleton, with no code of its own.
    LEFTOVER = "leftover" # Code that doesn't fit into any other category.
    MERGED_GROUP = "merged_group" # A group of chunks that have been merged together.
    FILE_OVERVIEW = "file_overview" # A synthetic chunk representing the entire file, with no code of its own.

class RefKind:
    """The values RefRecord.kind can take."""

    CALL = "call" # This reference is a function or method call.
    INHERITANCE = "inheritance"

class RefStatus:
    """The values RefRecord.status can take."""

    LOCAL = "local" # This reference points to a chunk defined in the same repository.
    EXTERNAL = "external"  # Third-party or standard library imports
    BUILTIN = "builtin"    # Language built-ins like print, len, console.log
    UNRESOLVED = "unresolved" # This reference could not be resolved to any known chunk in the repository.

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
    owner_name: str | None = None  # If this is a method call, the name of the class it was called on (if known); None otherwise.

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

    parent_chunk_id: str | None = None  # chunk_id of the enclosing DEFINITION/CLASS_SKELETON/
    # FUNCTION_SKELETON this chunk was carved out of (e.g. a LEFTOVER class field's enclosing
    # class, or a nested def's enclosing oversized function). None for top-level chunks.

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