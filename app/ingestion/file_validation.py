"""Heuristics for detecting empty, binary, or minified files."""
import os
from pathlib import Path

_TEXT_CHARACTERS = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)))
_BINARY_SAMPLE_SIZE = 1024
_MINIFIED_SAMPLE_SIZE = 8192
_MIN_LINES_FOR_CHECK = 10      # too few lines to judge reliably, don't flag
_LONG_LINE_THRESHOLD = 200     # a single "long" line, in chars
_LONG_LINE_RATIO = 0.7         # most lines in the sample must be long
_MIN_AVG_LINE_LENGTH = 200     # AND the average must also be high


def is_file_empty(file_path: str) -> bool:
    """Check if a file is empty."""
    try:
        return os.path.getsize(file_path) == 0
    except OSError as e:
        raise RuntimeError(f"Error checking file size for {file_path}: {e}") from e

def is_file_oversized(file_path: str, max_size_mb: int) -> bool:
    """Check if a file exceeds the maximum allowed size in megabytes."""
    try:
        size_bytes = os.path.getsize(file_path)
        return size_bytes > max_size_mb * 1024 * 1024
    except OSError as e:
        raise RuntimeError(f"Error checking file size for {file_path}: {e}") from e
    
def is_file_binary(content: bytes) -> bool:
    """Check if content is binary: NUL byte, or any non-text byte present."""
    sample = content[:_BINARY_SAMPLE_SIZE]
    if not sample:
        return False
    if b"\0" in sample:
        return True
    nontext = sample.translate(None, _TEXT_CHARACTERS)
    return bool(nontext)


def _has_minified_filename(file_path: str) -> bool:
    """Cheap fast-path: the widely-used .min.js / .min.ts naming convention."""
    return Path(file_path).stem.endswith(".min")


def is_file_minified(file_path: str, content: bytes) -> bool:
    """Check if content looks minified: dense, few-lined, consistently long lines."""
    if _has_minified_filename(file_path):
        return True

    was_truncated = len(content) > _MINIFIED_SAMPLE_SIZE
    sample = content[:_MINIFIED_SAMPLE_SIZE]
    lines = sample.splitlines()

    # Only drop the last line if sampling actually cut it off mid-line.
    if was_truncated and len(lines) > 1:
        lines = lines[:-1]

    if not lines:
        return False

    # Classic case: the whole file (or whole sample) is one giant line.
    if len(lines) == 1:
        return len(lines[0]) > _LONG_LINE_THRESHOLD

    long_line_count = sum(1 for line in lines if len(line) > _LONG_LINE_THRESHOLD)

    if len(lines) < _MIN_LINES_FOR_CHECK:
        return long_line_count == len(lines)  # every line is long -> minified

    long_line_ratio = long_line_count / len(lines)
    avg_line_length = sum(len(line) for line in lines) / len(lines)

    return (
        long_line_ratio >= _LONG_LINE_RATIO
        and avg_line_length > _MIN_AVG_LINE_LENGTH
    )