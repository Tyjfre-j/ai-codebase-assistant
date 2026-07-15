import logging

from app.core.exceptions import MalformedSourceError, TreeSitterParseError
from app.ingestion.chunking.chunk_pipeline import chunk_file
from app.ingestion.code_chunk import ParsedFileChunks
from app.ingestion.refs.extractor import extract_refs_for_file
from app.ingestion.source_file_scanner import iter_source_files
from app.ingestion.source_file_validation import (
    validate_file_thru_content,
    validate_file_thru_path,
)
from app.ingestion.source_parser import CodeParser

logger = logging.getLogger(__name__)


def chunk_repository(root: str, max_size_mb: int = 5, budget: int = 1500) -> list[ParsedFileChunks]:
    """Walk a repository, parse and chunk every supported source file, and collect
    per-file results with import metadata preserved for later reference resolution."""
    parser = CodeParser()
    extensions = set(parser.language_configs.keys())
    results: list[ParsedFileChunks] = []

    for file_path in iter_source_files(root, extensions):
        path_check = validate_file_thru_path(file_path, max_size_mb)
        if not path_check.is_valid:
            continue

        with open(file_path, "rb") as f:
            content = f.read()

        content_check = validate_file_thru_content(file_path, content)
        if not content_check.is_valid:
            continue

        try:
            parsed = parser.parse_file(file_path, content)
            chunks, import_text, import_ranges = chunk_file(file_path, parsed, budget)
            extract_refs_for_file(parsed, chunks)
        except (MalformedSourceError, TreeSitterParseError) as e:
            logger.warning("Skipping %s: %s", file_path, e)
            continue

        results.append(ParsedFileChunks(
            file_path=file_path,
            chunks=chunks,
            import_text=import_text,
            import_ranges=import_ranges,
        ))

    return results