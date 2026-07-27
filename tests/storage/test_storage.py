"""Tests for app/storage/ — persistence, retrieval, and schema correctness.

Run with: pytest tests/storage/test_storage.py -v
Requires: pytest, pytest-asyncio, aiosqlite
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from app.ingestion.code_chunk import (
    ChunkKind,
    CodeChunk,
    ParsedFileChunks,
    RefKind,
    RefRecord,
    RefStatus,
    RepositoryChunkResult,
    SkippedFile,
)
from app.storage.db import (
    get_callers,
    get_callees,
    get_chunk,
    get_chunk_by_name,
    get_chunks_by_file,
    init_db,
    get_connection,
    persist_repository,
    persist_single_file,
)
from app.storage.models import ChunkRow, RefRow
from app.retrieval.retrieval import (
    RetrievalContext,
    find_callers,
    find_callees,
    get_definition,
)


@pytest_asyncio.fixture
async def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    await init_db(db_path)
    conn = await get_connection(db_path)
    yield conn, db_path
    await conn.close()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    # File layout:
    #   foo(): pass
    #   bar(): foo()
    (repo / "main.py").write_text("def foo(): pass\ndef bar(): foo()\n")
    return repo


def _make_chunk(
    chunk_id: str,
    name: str,
    full_name: str,
    file_path: str,
    start_byte: int,
    end_byte: int,
    start_line: int,
    end_line: int,
    kind: str = ChunkKind.DEFINITION,
    refs: list[RefRecord] | None = None,
) -> CodeChunk:
    return CodeChunk(
        chunk_id=chunk_id,
        full_name=full_name,
        name=name,
        file_path=file_path,
        start_byte=start_byte,
        end_byte=end_byte,
        start_line=start_line,
        end_line=end_line,
        language="python",
        code="",
        kind=kind,
        size_chars=0,
        references=refs or [],
        contained_symbols=[],
    )


def _make_result(repo_root: Path) -> tuple[RepositoryChunkResult, dict[str, bytes]]:
    content = b"def foo(): pass\ndef bar(): foo()\n"
    file_path = "main.py"

    # Byte math:
    # "def foo(): pass\n" = 16 bytes (indices 0-15)
    # "def bar(): foo()\n" = 17 bytes (indices 16-32) -> file is 33 bytes total
    # Within "def bar(): foo()\n" (starts at absolute offset 16):
    #   "foo" is at relative offset 11-13 -> absolute 27-29, end_byte=30 (exclusive)
    foo_chunk = _make_chunk(
        chunk_id="foo_1", name="foo", full_name="foo",
        file_path=file_path, start_byte=0, end_byte=16,
        start_line=1, end_line=1,
    )
    bar_refs = [
        RefRecord(
            text="foo", kind=RefKind.CALL,
            points_to="foo_1", start_byte=27, end_byte=30,
            status=RefStatus.LOCAL,
        )
    ]
    bar_chunk = _make_chunk(
        chunk_id="bar_1", name="bar", full_name="bar",
        file_path=file_path, start_byte=16, end_byte=33,
        start_line=2, end_line=2,
        refs=bar_refs,
    )

    parsed = ParsedFileChunks(
        file_path=file_path,
        chunks=[foo_chunk, bar_chunk],
    )
    result = RepositoryChunkResult(files=[parsed], skipped=[])
    return result, {file_path: content}


# ---------------------------------------------------------------------------
# Schema / init
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_init_db_idempotent(tmp_db):
    """Running init_db twice on the same file must not error."""
    conn, db_path = tmp_db
    await conn.close()
    # Re-init on same path
    await init_db(db_path)
    conn2 = await get_connection(db_path)
    cur = await conn2.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row["name"] for row in await cur.fetchall()}
    assert "chunks" in tables
    assert "refs" in tables
    await conn2.close()


# ---------------------------------------------------------------------------
# Persistence roundtrip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_repository_roundtrip(tmp_db, tmp_repo):
    conn, _ = tmp_db
    result, file_contents = _make_result(tmp_repo)
    await persist_repository(conn, result, file_contents)

    chunks = await get_chunks_by_file(conn, "main.py")
    assert len(chunks) == 2
    names = {c.name for c in chunks}
    assert names == {"foo", "bar"}

    refs = await get_callees(conn, "bar_1")
    assert len(refs) == 1
    assert refs[0].points_to == "foo_1"
    assert refs[0].status == RefStatus.LOCAL


@pytest.mark.asyncio
async def test_repersist_same_file_replaces_old_chunks(tmp_db, tmp_repo):
    conn, _ = tmp_db
    result, file_contents = _make_result(tmp_repo)
    await persist_repository(conn, result, file_contents)

    # Re-persist identical data
    await persist_repository(conn, result, file_contents)

    chunks = await get_chunks_by_file(conn, "main.py")
    assert len(chunks) == 2
    # Verify no duplicate rows
    cur = await conn.execute("SELECT COUNT(*) as cnt FROM chunks")
    row = await cur.fetchone()
    assert row["cnt"] == 2


@pytest.mark.asyncio
async def test_two_pass_ref_resolution(tmp_db, tmp_repo):
    """Refs to chunks in later-processed files must resolve."""
    conn, _ = tmp_db
    result, file_contents = _make_result(tmp_repo)
    await persist_repository(conn, result, file_contents)

    callee = await get_chunk(conn, "foo_1")
    assert callee is not None
    callers = await get_callers(conn, "foo_1")
    assert len(callers) == 1
    assert callers[0].chunk.name == "bar"


@pytest.mark.asyncio
async def test_self_referential_edge(tmp_db, tmp_repo):
    """A chunk that calls itself must store and query without error."""
    conn, _ = tmp_db
    content = b"def rec(): rec()\n"
    chunk = _make_chunk(
        chunk_id="rec_1", name="rec", full_name="rec",
        file_path="main.py", start_byte=0, end_byte=16,
        start_line=1, end_line=1,
        refs=[
            RefRecord(
                text="rec", kind=RefKind.CALL,
                points_to="rec_1", start_byte=11, end_byte=14,
                status=RefStatus.LOCAL,
            )
        ],
    )
    parsed = ParsedFileChunks(file_path="main.py", chunks=[chunk])
    result = RepositoryChunkResult(files=[parsed], skipped=[])
    await persist_repository(conn, result, {"main.py": content})

    callers = await get_callers(conn, "rec_1")
    assert len(callers) == 1
    assert callers[0].chunk.chunk_id == "rec_1"


@pytest.mark.asyncio
async def test_stale_flag_set_on_rechunk(tmp_db, tmp_repo):
    """Re-chunking a file marks refs pointing into its old chunks as stale."""
    conn, _ = tmp_db

    # First: persist a.py and b.py with cross-file ref
    content_a = b"def foo(): pass\n"
    foo = _make_chunk(
        chunk_id="foo_a", name="foo", full_name="foo",
        file_path="a.py", start_byte=0, end_byte=16,
        start_line=1, end_line=1,
    )
    content_b = b"def bar(): foo()\n"
    bar = _make_chunk(
        chunk_id="bar_b", name="bar", full_name="bar",
        file_path="b.py", start_byte=0, end_byte=17,
        start_line=1, end_line=1,
        refs=[
            RefRecord(
                text="foo", kind=RefKind.CALL,
                points_to="foo_a", start_byte=11, end_byte=14,
                status=RefStatus.LOCAL,
            )
        ],
    )
    result = RepositoryChunkResult(
        files=[
            ParsedFileChunks(file_path="a.py", chunks=[foo]),
            ParsedFileChunks(file_path="b.py", chunks=[bar]),
        ],
        skipped=[],
    )
    await persist_repository(conn, result, {"a.py": content_a, "b.py": content_b})

    # Re-persist a.py with foo changed (new chunk_id)
    foo_v2 = _make_chunk(
        chunk_id="foo_a2", name="foo", full_name="foo",
        file_path="a.py", start_byte=0, end_byte=16,
        start_line=1, end_line=1,
    )
    await persist_single_file(
        conn,
        ParsedFileChunks(file_path="a.py", chunks=[foo_v2]),
        content_a,
    )

    # The ref from bar_b pointing to foo_a should now be stale
    cur = await conn.execute("SELECT stale FROM refs WHERE source_chunk_id = 'bar_b'")
    row = await cur.fetchone()
    assert row["stale"] == 1


@pytest.mark.asyncio
async def test_status_not_mutated_on_stale(tmp_db, tmp_repo):
    """Stale refs keep their original status, not changed to 'unresolved'."""
    conn, _ = tmp_db

    content_a = b"def foo(): pass\n"
    foo = _make_chunk(
        chunk_id="foo_a", name="foo", full_name="foo",
        file_path="a.py", start_byte=0, end_byte=16,
        start_line=1, end_line=1,
    )
    content_b = b"def bar(): foo()\n"
    bar = _make_chunk(
        chunk_id="bar_b", name="bar", full_name="bar",
        file_path="b.py", start_byte=0, end_byte=17,
        start_line=1, end_line=1,
        refs=[
            RefRecord(
                text="foo", kind=RefKind.CALL,
                points_to="foo_a", start_byte=11, end_byte=14,
                status=RefStatus.LOCAL,
            )
        ],
    )
    await persist_repository(
        conn,
        RepositoryChunkResult(
            files=[
                ParsedFileChunks(file_path="a.py", chunks=[foo]),
                ParsedFileChunks(file_path="b.py", chunks=[bar]),
            ],
            skipped=[],
        ),
        {"a.py": content_a, "b.py": content_b},
    )

    foo_v2 = _make_chunk(
        chunk_id="foo_a2", name="foo", full_name="foo",
        file_path="a.py", start_byte=0, end_byte=16,
        start_line=1, end_line=1,
    )
    await persist_single_file(
        conn,
        ParsedFileChunks(file_path="a.py", chunks=[foo_v2]),
        content_a,
    )

    cur = await conn.execute(
        "SELECT status, stale FROM refs WHERE source_chunk_id = 'bar_b'"
    )
    row = await cur.fetchone()
    assert row["status"] == RefStatus.LOCAL
    assert row["stale"] == 1


# ---------------------------------------------------------------------------
# Read queries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_definition_exact_match(tmp_db, tmp_repo):
    conn, _ = tmp_db
    result, file_contents = _make_result(tmp_repo)
    await persist_repository(conn, result, file_contents)

    ctx = RetrievalContext(conn=conn, repo_root=tmp_repo)
    defs = await get_definition(ctx, "foo")
    assert len(defs) == 1
    assert defs[0].name == "foo"

    defs_full = await get_definition(ctx, "foo")
    assert len(defs_full) == 1


@pytest.mark.asyncio
async def test_find_callers_local_only(tmp_db, tmp_repo):
    conn, _ = tmp_db
    result, file_contents = _make_result(tmp_repo)
    await persist_repository(conn, result, file_contents)

    ctx = RetrievalContext(conn=conn, repo_root=tmp_repo)
    callers = await find_callers(ctx, "foo")
    assert len(callers) == 1
    assert callers[0].name == "bar"


@pytest.mark.asyncio
async def test_find_callers_dedup(tmp_db, tmp_repo):
    """Multiple refs from the same caller chunk should produce one result."""
    conn, _ = tmp_db
    content = b"def bar(): foo(); foo()\n"
    # "def bar(): foo(); foo()\n" is 24 bytes (indices 0-23).
    # First "foo" at 11-13 (end_byte=14). Second "foo" at 18-20 (end_byte=21).
    bar = _make_chunk(
        chunk_id="bar_1", name="bar", full_name="bar",
        file_path="main.py", start_byte=0, end_byte=24,
        start_line=1, end_line=1,
        refs=[
            RefRecord(
                text="foo", kind=RefKind.CALL,
                points_to="foo_1", start_byte=11, end_byte=14,
                status=RefStatus.LOCAL,
            ),
            RefRecord(
                text="foo", kind=RefKind.CALL,
                points_to="foo_1", start_byte=18, end_byte=21,
                status=RefStatus.LOCAL,
            ),
        ],
    )
    foo = _make_chunk(
        chunk_id="foo_1", name="foo", full_name="foo",
        file_path="main.py", start_byte=0, end_byte=0,
        start_line=0, end_line=0,
    )
    result = RepositoryChunkResult(
        files=[ParsedFileChunks(file_path="main.py", chunks=[foo, bar])],
        skipped=[],
    )
    await persist_repository(conn, result, {"main.py": content})

    ctx = RetrievalContext(conn=conn, repo_root=tmp_repo)
    callers = await find_callers(ctx, "foo")
    assert len(callers) == 1


@pytest.mark.asyncio
async def test_find_callees_dedup(tmp_db, tmp_repo):
    """Multiple refs to the same callee chunk should produce one result."""
    conn, _ = tmp_db
    content = b"def bar(): foo(); foo()\n"
    # Same byte math as test_find_callers_dedup above.
    bar = _make_chunk(
        chunk_id="bar_1", name="bar", full_name="bar",
        file_path="main.py", start_byte=0, end_byte=24,
        start_line=1, end_line=1,
        refs=[
            RefRecord(
                text="foo", kind=RefKind.CALL,
                points_to="foo_1", start_byte=11, end_byte=14,
                status=RefStatus.LOCAL,
            ),
            RefRecord(
                text="foo", kind=RefKind.CALL,
                points_to="foo_1", start_byte=18, end_byte=21,
                status=RefStatus.LOCAL,
            ),
        ],
    )
    foo = _make_chunk(
        chunk_id="foo_1", name="foo", full_name="foo",
        file_path="main.py", start_byte=0, end_byte=0,
        start_line=0, end_line=0,
    )
    result = RepositoryChunkResult(
        files=[ParsedFileChunks(file_path="main.py", chunks=[foo, bar])],
        skipped=[],
    )
    await persist_repository(conn, result, {"main.py": content})

    ctx = RetrievalContext(conn=conn, repo_root=tmp_repo)
    callees = await find_callees(ctx, "bar")
    assert len(callees) == 1
    assert callees[0].name == "foo"


@pytest.mark.asyncio
async def test_chunk_code_sliced_from_disk(tmp_db, tmp_repo):
    """CodeResult.code must match the actual source file bytes."""
    conn, _ = tmp_db
    result, file_contents = _make_result(tmp_repo)
    await persist_repository(conn, result, file_contents)

    ctx = RetrievalContext(conn=conn, repo_root=tmp_repo)
    defs = await get_definition(ctx, "foo")
    assert len(defs) == 1
    # foo chunk: start_byte=0, end_byte=16 -> "def foo(): pass\n"
    assert defs[0].code == "def foo(): pass\n"


@pytest.mark.asyncio
async def test_ref_byte_range_matches_ref_text(tmp_db, tmp_repo):
    """A ref's own start_byte/end_byte must slice out exactly its `text`.

    This is the check the earlier fixtures were missing: every other test
    here only asserts on points_to/status/name, so a wrong byte offset on a
    RefRecord could pass the whole suite silently. This slices the ref's
    bytes directly from the file the way retrieval eventually would, and
    checks it against the ref's own recorded text.
    """
    conn, _ = tmp_db
    result, file_contents = _make_result(tmp_repo)
    await persist_repository(conn, result, file_contents)

    content = file_contents["main.py"]
    callees = await get_callees(conn, "bar_1")
    assert len(callees) == 1
    ref = callees[0]
    assert content[ref.start_byte:ref.end_byte] == ref.text.encode("utf-8")