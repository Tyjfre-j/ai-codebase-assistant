from dataclasses import dataclass, field


@dataclass
class RefRecord:
    """One reference (a call or an inheritance) found inside a chunk's code."""

    text: str  # What was literally written at the reference site, e.g. "get_user", "self.get_user", "Base".
    kind: str  # "call" (this invokes something) or "inheritance" (this extends something).
    points_to: str | None  # The chunk_id this reference resolves to, once we know it; None until then.
    status: str = "unresolved"  # "local", "external" (not yet implemented), or "unresolved".

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
    kind: str  # "definition", "class_skeleton", "leftover", or "merged_group" -- what role this chunk plays.
    merged_names: list[str] | None  # The original names bundled in here, if kind is "merged_group".

    size_chars: int  # How many characters of code this chunk holds.

    references: list[RefRecord] = field(default_factory=list)  # Filled in later, once refs are extracted.


@dataclass
class ParsedFileChunks:
    """Everything produced by chunking one file, plus its import info for later resolution."""

    file_path: str  # The file this came from.
    chunks: list[CodeChunk]  # Every chunk found in this file.
    import_text: str  # The raw text of this file's imports.
    import_ranges: list[tuple[int, int]]  # Where each import statement sits in the file.
    import_bindings: dict[str, tuple[str | None, str]] = field(default_factory=dict)
    # Maps each name used in the code to (the file it actually comes from, or None; its original name).