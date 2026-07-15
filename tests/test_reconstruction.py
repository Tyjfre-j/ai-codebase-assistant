import os

import pytest

from app.ingestion.chunking.chunk_pipeline import chunk_file
from app.ingestion.source_parser import CodeParser

parser = CodeParser()

FIXTURES = [
    "tests/fixtures/python/sample.py",
    "tests/fixtures/go/sample.go",
    "tests/fixtures/javascript/sample.js",
    "tests/fixtures/typescript/sample.ts",
]

def _assert_whitespace_gap(start, end, content):
    gap = content[start:end]
    assert gap.strip() == b"", f"non-whitespace bytes dropped between {start} and {end}: {gap!r}"


@pytest.mark.parametrize("fixture_path", FIXTURES)
def test_reconstruction_invariant(fixture_path):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), fixture_path)
    content = open(path, "rb").read()
    parsed = parser.parse_file(path, content)
    chunks, import_text, import_ranges = chunk_file(path, parsed)
    all_ranges = [
        (c.start_byte, c.end_byte) for c in chunks if c.kind != "class_skeleton"
    ] + import_ranges
    all_ranges.sort()
    cursor = 0
    for start, end in all_ranges:
        assert start >= cursor, (
            f"overlapping spans detected: span [{start}:{end}] starts before "
            f"cursor={cursor} (previous span ended there or later)"
        )
        if start > cursor:
            _assert_whitespace_gap(cursor, start, content)
        cursor = max(cursor, end)
    if cursor < len(content):
        _assert_whitespace_gap(cursor, len(content), content)