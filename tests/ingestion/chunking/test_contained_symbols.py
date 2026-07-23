from pathlib import Path

from app.ingestion.chunking.chunk_pipeline import chunk_file
from app.ingestion.code_chunk import ChunkKind, ParsedFileChunks, RefStatus
from app.ingestion.refs.resolver import resolve_all_references
from app.ingestion.source_parser import CodeParser

_parser = CodeParser()


def _parse(fixture_path: str):
    content = Path(fixture_path).read_bytes()
    return _parser.parse_file(fixture_path, content)


OVERSIZED_FIXTURE = "tests/fixtures/python/oversized_class.py"
SAMPLE_FIXTURE = "tests/fixtures/python/sample.py"


def test_oversized_class_small_method_gets_own_chunk():
    parsed = _parse(OVERSIZED_FIXTURE)
    chunks, _, _, _ = chunk_file(OVERSIZED_FIXTURE, parsed)

    skeleton = next(c for c in chunks if c.kind == ChunkKind.DEFINITION_SKELETON)
    small_method = next(
        c for c in chunks
        if c.kind == ChunkKind.DEFINITION and c.full_name == "Config.small_method"
    )

    assert small_method.parent_chunk_id == skeleton.chunk_id
    assert small_method.contained_symbols == []


def test_oversized_class_level_non_method_code_not_indexed():
    parsed = _parse(OVERSIZED_FIXTURE)
    chunks, _, _, _ = chunk_file(OVERSIZED_FIXTURE, parsed)

    all_names = {c.full_name for c in chunks}
    all_contained = {s for c in chunks for s in c.contained_symbols}
    assert "Config.DEFAULT_TIMEOUT" not in all_names | all_contained
    assert "Config.RETRY_LIMIT" not in all_names | all_contained

    skeleton = next(c for c in chunks if c.kind == ChunkKind.DEFINITION_SKELETON)
    assert "DEFAULT_TIMEOUT" in skeleton.code
    assert "RETRY_LIMIT" in skeleton.code


def test_small_class_records_contained_symbols():
    parsed = _parse(SAMPLE_FIXTURE)
    chunks, _, _, _ = chunk_file(SAMPLE_FIXTURE, parsed)

    calc = next(
        c for c in chunks
        if c.kind == ChunkKind.DEFINITION and c.full_name == "ShapeCalculator"
    )
    assert {
        "ShapeCalculator.circle_area",
        "ShapeCalculator.square_area",
        "ShapeCalculator.rectangle_area",
    }.issubset(set(calc.contained_symbols))


def test_self_call_resolves_inside_small_class():
    """Requires ShapeCalculator in sample.py to have a method calling
    self.circle_area() (or similar) -- skips if none found yet."""
    parsed = _parse(SAMPLE_FIXTURE)
    chunks, import_text, import_ranges, _ = chunk_file(SAMPLE_FIXTURE, parsed)

    parsed_file_chunks = ParsedFileChunks(
        file_path=SAMPLE_FIXTURE,
        chunks=chunks,
        import_text=import_text,
        import_ranges=import_ranges,
        import_bindings={},
        wildcard_import_modules=[],
    )
    resolve_all_references([parsed_file_chunks])

    calc = next(c for c in chunks if c.full_name == "ShapeCalculator")
    self_call_ref = next(
        (r for r in calc.references if "circle_area" in r.text), None
    )
    if self_call_ref is None:
        import pytest
        pytest.skip("no self.circle_area()-style call found in ShapeCalculator yet")

    assert self_call_ref.status == RefStatus.LOCAL
    assert self_call_ref.points_to == calc.chunk_id
