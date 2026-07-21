from dataclasses import dataclass, field


class ChunkKind:
    """The canonical set of values CodeChunk.kind can take."""

    DEFINITION = "definition"
    # A function, method, class, or interface member — kept in full.

    DEFINITION_SKELETON = "definition_skeleton"
    # A synthetic stub for an oversized definition (class, function, or interface).
    # Signature line + one-liner stubs for any nested definitions that got their own chunk.

    FILE_SKELETON = "file_skeleton"
    # A synthetic chunk representing a file's top-level skeleton.


class RefKind:
    """The values RefRecord.kind can take."""

    CALL = "call"
    # A function or method call.

    INHERITANCE = "inheritance"
    # A class or interface inheritance / extension.


class RefStatus:
    """The values RefRecord.status can take."""

    LOCAL = "local"
    # Resolved to a chunk defined in the same repository.

    EXTERNAL = "external"
    # Third-party or standard-library import (unresolvable within the repo).

    BUILTIN = "builtin"
    # Language built-in like print, len, console.log.

    UNRESOLVED = "unresolved"
    # Could not be resolved to any known chunk.


class ImportKind:
    """The values an import binding's kind can take."""

    MODULE = "module"
    # e.g. `import os` -> "os" binds the whole module.

    NAMED = "named"
    # e.g. `from os import path` -> "path" binds one specific symbol.


@dataclass
class RefRecord:
    """One reference (a call or an inheritance) found inside a chunk's code."""

    text: str
    # What was literally written at the reference site, e.g. "get_user",
    # "self.get_user", "Base".

    kind: str
    # RefKind.CALL or RefKind.INHERITANCE.

    points_to: str | None = None
    # The chunk_id this reference resolves to; None until resolved.

    start_byte: int = 0
    # Where this reference site starts in the source file.

    end_byte: int = 0
    # Where this reference site ends.

    status: str = RefStatus.UNRESOLVED
    # LOCAL, EXTERNAL, BUILTIN, or UNRESOLVED.


@dataclass
class CodeChunk:
    """One retrievable piece of a source file."""

    chunk_id: str
    # Stable identifier used to point at this chunk from elsewhere.

    full_name: str
    # Fully qualified name including namespace, e.g. "ShapeCalculator.circle_area".

    name: str
    # This chunk's own name, e.g. "circle_area"; "<anonymous>" if unnamed.

    defined_in_class: str | None = None
    # The class this lives inside, if any. When set, full_name is
    # typically f"{defined_in_class}.{name}".

    file_path: str
    # Which file this chunk came from.

    start_byte: int
    # Where this chunk starts in the source file.

    end_byte: int
    # Where this chunk ends. Same as start_byte for empty skeleton chunks.

    start_line: int
    # 1-indexed start line. Needed to resolve grep (file, line) hits to a chunk.

    end_line: int
    # 1-indexed end line. Same as start_line for empty skeleton chunks.

    language: str
    # "python", "go", "javascript", "typescript", etc.

    code: str
    # The actual text of this chunk, or a synthetic stub for skeletons.

    docstring: str | None = None
    # Reserved for later; always None for now.

    node_type: str | None = None
    # The tree-sitter node type, e.g. "function_definition" or "class_definition".

    kind: str = ChunkKind.DEFINITION
    # DEFINITION, DEFINITION_SKELETON, or FILE_SKELETON.

    size_chars: int = 0
    # Character count of this chunk's code.

    parent_chunk_id: str | None = None
    # chunk_id of the enclosing definition this was carved out of.
    # None for top-level chunks.

    references: list[RefRecord] = field(default_factory=list)
    # Filled in during reference extraction and resolution.

    contained_symbols: list[str] = field(default_factory=list)
    # full_names of nested definitions folded into this chunk rather than
    # emitted as separate chunks. Empty for leaf definitions.


@dataclass
class ParsedFileChunks:
    """Everything produced by chunking one file, plus import info for resolution."""

    file_path: str
    # The file this came from.

    chunks: list[CodeChunk]
    # Every chunk found in this file.

    import_text: str
    # Raw text of this file's import statements.

    import_ranges: list[tuple[int, int]]
    # Byte ranges of each import statement in the file.

    import_bindings: dict[str, tuple[str | None, str, str]] = field(default_factory=dict)
    # Maps each imported alias/name to (resolved_path_or_None, bound_name, import_kind).


@dataclass
class SkippedFile:
    """One file that didn't make it into the chunk output, and why."""

    file_path: str
    reason: str
    # "empty", "oversized", "binary", "minified", an OSError, or an exception class name.


@dataclass
class RepositoryChunkResult:
    """Everything `chunk_repository` produces."""

    files: list[ParsedFileChunks]
    skipped: list[SkippedFile]

    def skip_counts_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for skipped_file in self.skipped:
            counts[skipped_file.reason] = counts.get(skipped_file.reason, 0) + 1
        return counts
