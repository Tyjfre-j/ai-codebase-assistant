import logging

from app.core.constants import DEFAULT_CHUNK_BUDGET_CHARS, DEFAULT_MAX_FILE_SIZE_MB
from app.core.exceptions import (
    ChunkExtractionError,
    InvalidChunkBudgetError,
    MalformedSourceError,
    TreeSitterParseError,
)
from app.ingestion.chunking.chunk_pipeline import chunk_file
from app.ingestion.code_chunk import ParsedFileChunks, RepositoryChunkResult, SkippedFile
from app.ingestion.refs.import_bindings import extract_import_bindings_for_file
from app.ingestion.refs.resolver import resolve_all_chunk_references
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
    budget: int = DEFAULT_CHUNK_BUDGET_CHARS,
) -> RepositoryChunkResult:
    """Walk a repository, parse and chunk every supported source file, and collect per-file results.

    Returns both the successful results and a per-file skip summary — a repo
    that silently drops a large fraction of its files (e.g. from a grammar
    edge case) should be visible to the caller without grepping logs.
    """

    # Validate chunk size budget before doing any work, so we don't waste time parsing a repo
    if budget <= 0:
        raise InvalidChunkBudgetError(f"budget must be positive, got {budget}")
    
    # parser initialization, loads all grammars and language configs and used for all files
    parser = CodeParser()

    # Get the set of file extensions that the parser can handle
    extensions = set(parser.language_configs.keys())

    # Initialize the results and skipped lists to collect per-file results
    results: list[ParsedFileChunks] = []
    skipped: list[SkippedFile] = []

    # loop through all source files in the repo, filtering by supported extensions
    for file_path in iter_source_files(root, extensions):

        # run path validation checks (check if file is empty or oversized) before reading the file content
        # check app/ingestion/source_file_validation.py for details on what each check does
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

        # run content validation checks (check if file is binary or minified) after reading the file content
        # check app/ingestion/source_file_validation.py for details on what each check does
        content_check = validate_file_thru_content(file_path, content)
        if not content_check.is_valid:
            skipped.append(SkippedFile(file_path=file_path, reason=content_check.reason.value if content_check.reason else "unknown"))
            continue

        try:
            # parse the file to get a ParsedFile object, which contains the AST and other metadata
            # check app/ingestion/source_parser.py for details on what the ParsedFile object contains
            parsed = parser.parse_file(file_path, content)

            # chunk the file to get the list of CodeChunk objects, import text, import ranges, and captures
            # check app/ingestion/chunking/chunk_pipeline.py for details on what each of these outputs contains
            chunks, import_text, import_ranges, captures = chunk_file(file_path, parsed, budget)

            # map the import bindings for the file
            # check app/ingestion/refs/import_bindings.py for details on what the import_bindings output contains
            import_bindings = extract_import_bindings_for_file(parsed, file_path, root, captures)
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
        ))

    # After all files have been processed, resolve all references in the chunks to their corresponding definitions
    # check app/ingestion/refs/resolver.py for details on how references are resolved
    resolve_all_chunk_references(results)
    
    # Return the final RepositoryChunkResult object, which contains the successful results and the skipped files
    result = RepositoryChunkResult(files=results, skipped=skipped)

    if skipped:
        # Log a warning with the count of skipped files and the reasons for skipping them
        counts = result.skip_counts_by_reason()
        logger.warning(
            "Skipped %d file(s) during ingestion: %s",
            len(skipped),
            ", ".join(f"{reason}={count}" for reason, count in counts.items()),
        )

    return result