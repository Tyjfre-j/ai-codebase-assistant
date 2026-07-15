import pytest

from app.ingestion.repo_chunker import chunk_repository


FIXTURES_ROOT = "tests/fixtures"


@pytest.mark.parametrize("language,expected_ext", [
    ("python", ".py"),
    ("go", ".go"),
    ("javascript", ".js"),
])
def test_chunk_repository_produces_definition_chunks(language, expected_ext):
    results = chunk_repository(f"{FIXTURES_ROOT}/{language}")
    assert len(results) == 1, f"expected exactly one file parsed for {language}"
    parsed_chunks = results[0]
    assert parsed_chunks.file_path.endswith(expected_ext)
    definition_chunks = [c for c in parsed_chunks.chunks if c.kind == "definition"]
    assert len(definition_chunks) > 0, f"expected at least one definition chunk for {language}"


def test_python_fixture_has_expected_symbols():
    results = chunk_repository(f"{FIXTURES_ROOT}/python")
    parsed_chunks = results[0]

    all_symbol_names = {c.name for c in parsed_chunks.chunks}
    definition_symbol_names = {c.name for c in parsed_chunks.chunks if c.kind == "definition"}

    # ShapeCalculator has methods, so the class itself becomes a class_skeleton chunk,
    # not a "definition" -- its methods are the definition chunks, each carrying
    # defined_in_class == "ShapeCalculator".
    assert "ShapeCalculator" in all_symbol_names
    assert "standalone_helper" in definition_symbol_names
    assert "circle_area" in definition_symbol_names

    circle_area_chunk = next(c for c in parsed_chunks.chunks if c.name == "circle_area")
    assert circle_area_chunk.defined_in_class == "ShapeCalculator"


def test_python_fixture_refs_have_ref_kind_set():
    results = chunk_repository(f"{FIXTURES_ROOT}/python")
    parsed_chunks = results[0]
    all_refs = [ref for c in parsed_chunks.chunks for ref in c.references]
    assert len(all_refs) > 0
    for ref in all_refs:
        assert ref.kind in ("call", "inheritance")
        assert ref.status == "unresolved"


def test_python_fixture_standalone_helper_calls_os_path_exists():
    results = chunk_repository(f"{FIXTURES_ROOT}/python")
    parsed_chunks = results[0]
    helper_chunk = next(
        c for c in parsed_chunks.chunks
        if c.kind == "definition" and c.name == "standalone_helper"
    )
    raw_names = [ref.text for ref in helper_chunk.references]
    assert "os.path.exists" in raw_names


def test_python_class_skeleton_captures_inheritance_reference():
    parser_source = (
        "class Base:\n"
        "    pass\n\n"
        "class Child(Base):\n"
        "    def work(self):\n"
        "        return 1\n"
    )
    from app.ingestion.chunking.chunk_pipeline import chunk_file
    from app.ingestion.source_parser import CodeParser

    parser = CodeParser()
    parsed = parser.parse_file("sample.py", parser_source.encode("utf-8"))
    chunks, _, _ = chunk_file("sample.py", parsed)

    skeleton = next(c for c in chunks if c.kind == "class_skeleton" and c.name == "Child")
    assert [ref.kind for ref in skeleton.references] == ["inheritance"]
    assert [ref.text for ref in skeleton.references] == ["Base"]