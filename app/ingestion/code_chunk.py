from dataclasses import dataclass, field


class ChunkKind:
    DEFINITION = "definition"
    DEFINITION_SKELETON = "definition_skeleton"
    FILE_SKELETON = "file_skeleton"


class RefKind:
    CALL = "call"
    INHERITANCE = "inheritance"


class RefStatus:
    LOCAL = "local"
    EXTERNAL = "external"
    BUILTIN = "builtin"
    UNRESOLVED = "unresolved"


class ImportKind:
    MODULE = "module"
    NAMED = "named"


@dataclass
class RefRecord:
    text: str
    kind: str
    points_to: str | None = None
    start_byte: int = 0
    end_byte: int = 0
    status: str = RefStatus.UNRESOLVED


@dataclass
class ImportBinding:
    local_name: str
    resolved_path: str | None
    remote_name: str
    kind: str
    extra_segments: int = 0


@dataclass
class CodeChunk:
    chunk_id: str
    full_name: str
    name: str
    file_path: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    language: str
    code: str
    defined_in_class: str | None = None
    node_type: str | None = None
    kind: str = ChunkKind.DEFINITION
    size_chars: int = 0
    parent_chunk_id: str | None = None
    references: list[RefRecord] = field(default_factory=list)
    contained_symbols: list[str] = field(default_factory=list)


@dataclass
class ParsedFileChunks:
    file_path: str
    chunks: list[CodeChunk]
    import_text: str = ""
    import_ranges: list[tuple[int, int]] = field(default_factory=list)
    import_bindings: dict[str, ImportBinding] = field(default_factory=dict)
    wildcard_import_modules: list[str] = field(default_factory=list)


@dataclass
class SkippedFile:
    file_path: str
    reason: str


@dataclass
class RepositoryChunkResult:
    files: list[ParsedFileChunks]
    skipped: list[SkippedFile]

    def skip_counts_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for skipped_file in self.skipped:
            counts[skipped_file.reason] = counts.get(skipped_file.reason, 0) + 1
        return counts