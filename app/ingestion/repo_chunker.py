import logging

from app.core.constants import DEFAULT_CHUNK_INCLUSION_BUDGET_CHARS, DEFAULT_FILE_SKELETON_THRESHOLD_CHARS, DEFAULT_MAX_FILE_SIZE_MB
from app.core.exceptions import (
    ChunkExtractionError,
    InvalidChunkBudgetError,
    MalformedSourceError,
    TreeSitterParseError,
)
from app.ingestion.chunking.chunk_pipeline import chunk_file
from app.ingestion.code_chunk import ParsedFileChunks, RepositoryChunkResult, SkippedFile
from app.ingestion.refs.extract_import_bindings import extract_import_bindings_for_file
from app.ingestion.refs.resolver import resolve_all_references
from app.ingestion.source_file_scanner import iter_source_files
from app.ingestion.source_file_validation import (
    validate_file_thru_content,
    validate_file_thru_path,
)
from app.ingestion.source_parser import CodeParser

logger = logging.getLogger(__name__)


def chunk_repository(
    root: str,
    max_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB,
    skeleton_budget: int = DEFAULT_FILE_SKELETON_THRESHOLD_CHARS,
    budget: int = DEFAULT_CHUNK_INCLUSION_BUDGET_CHARS,
) -> RepositoryChunkResult:
    """Walk a repository, parse and chunk every supported source file, and collect per-file results."""

    if budget <= 0:
        raise InvalidChunkBudgetError(f"budget must be positive, got {budget}")

    if skeleton_budget <= 0:
        raise InvalidChunkBudgetError(f"skeleton_budget must be positive, got {skeleton_budget}")
    
    parser = CodeParser()
    extensions = set(parser.language_configs.keys())

    results: list[ParsedFileChunks] = []
    skipped: list[SkippedFile] = []

    for file_path in iter_source_files(root, extensions):
        path_check = validate_file_thru_path(file_path, max_size_mb)
        if not path_check.is_valid:
            skipped.append(SkippedFile(file_path=file_path, reason=path_check.reason.value if path_check.reason else "unknown"))
            continue

        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except OSError as e:
            logger.warning("Skipping %s: %s", file_path, e)
            skipped.append(SkippedFile(file_path=file_path, reason=type(e).__name__))
            continue

        content_check = validate_file_thru_content(file_path, content)
        if not content_check.is_valid:
            skipped.append(SkippedFile(file_path=file_path, reason=content_check.reason.value if content_check.reason else "unknown"))
            continue

        try:
            parsed = parser.parse_file(file_path, content)
            chunks, import_text, import_ranges, captures = chunk_file(file_path, parsed, budget, skeleton_budget)
            import_bindings, wildcard_modules = extract_import_bindings_for_file(parsed, file_path, root, captures)
        except (MalformedSourceError, TreeSitterParseError, ChunkExtractionError) as e:
            logger.warning("Skipping %s: %s", file_path, e)
            skipped.append(SkippedFile(file_path=file_path, reason=type(e).__name__))
            continue

        results.append(ParsedFileChunks(
            file_path=file_path,
            chunks=chunks,
            import_text=import_text,
            import_ranges=import_ranges,
            import_bindings=import_bindings,
            wildcard_import_modules=wildcard_modules,
        ))

    resolve_all_references(results)
    result = RepositoryChunkResult(files=results, skipped=skipped)

    if skipped:
        counts = result.skip_counts_by_reason()
        logger.warning(
            "Skipped %d file(s) during ingestion: %s",
            len(skipped),
            ", ".join(f"{reason}={count}" for reason, count in counts.items()),
        )

    return result