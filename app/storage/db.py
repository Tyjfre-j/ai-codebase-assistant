"""SQLite persistence for chunking + ref extraction output.

Matches app/ingestion/code_chunk.py exactly (CodeChunk, RefRecord,
ParsedFileChunks, RepositoryChunkResult, SkippedFile). See schema.sql.

SQL text lives in queries.py; this module owns connection lifecycle,
control flow, and shaping results into typed dataclasses (models.py).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import aiosqlite

from app.ingestion.code_chunk import (
    CodeChunk,
    ParsedFileChunks,
    RepositoryChunkResult,
)
from app.storage import queries as q
from app.storage.models import CallerRow, ChunkRow, RefRow

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def get_connection(db_path: str | Path) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute("PRAGMA journal_mode = WAL")
    return conn


async def init_db(db_path: str | Path) -> None:
    conn = await get_connection(db_path)
    try:
        await conn.executescript(SCHEMA_PATH.read_text())
        await conn.commit()
    finally:
        await conn.close()


def _hash_content(file_content: bytes) -> str:
    return hashlib.sha1(file_content).hexdigest()


def _placeholders(items: list) -> str:
    return ",".join("?" for _ in items)


async def _mark_referencing_refs_stale(conn: aiosqlite.Connection, chunk_ids: list[str]) -> None:
    """Flag refs elsewhere in the repo that point into chunks we're about to
    replace, per the lazy cross-file ref-resolution decision (Decision #15).
    Called BEFORE deleting the old chunks for a file, since deleting them
    first would cascade-null the points_to values we need to match on.
    """
    if not chunk_ids:
        return
    sql = q.MARK_REFS_STALE_BY_TARGET.format(placeholders=_placeholders(chunk_ids))
    await conn.execute(sql, chunk_ids)

async def persist_chunks_only(
    conn: aiosqlite.Connection,
    parsed: ParsedFileChunks,
    file_content: bytes,
) -> None:
    """Upsert one file's chunks. Delete-then-reinsert per file so re-chunking
    a file never leaves orphaned chunks behind. Marks referencing refs stale
    before recomputing this file's chunks.
    """
    content_hash = _hash_content(file_content)
    language = parsed.chunks[0].language if parsed.chunks else None

    await conn.execute(q.UPSERT_FILE, (parsed.file_path, content_hash, language))

    cur = await conn.execute(q.SELECT_CHUNK_IDS_BY_FILE, (parsed.file_path,))
    old_chunk_ids = [row["chunk_id"] for row in await cur.fetchall()]
    await _mark_referencing_refs_stale(conn, old_chunk_ids)

    # Delete refs whose SOURCE is in this file BEFORE deleting chunks,
    # to avoid FK constraint violations (refs.source_chunk_id -> chunks.chunk_id).
    await conn.execute(q.DELETE_REFS_BY_FILE, (parsed.file_path,))

    await conn.execute(q.DELETE_CHUNKS_BY_FILE, (parsed.file_path,))
    if old_chunk_ids:
        sql = q.DELETE_CHUNKS_FTS_BY_ID.format(placeholders=_placeholders(old_chunk_ids))
        await conn.execute(sql, old_chunk_ids)

    for chunk in parsed.chunks:
        await conn.execute(
            q.INSERT_CHUNK,
            (
                chunk.chunk_id, chunk.full_name, chunk.name, chunk.file_path,
                chunk.start_byte, chunk.end_byte, chunk.start_line, chunk.end_line,
                chunk.language, chunk.defined_in_class, chunk.node_type, chunk.kind,
                chunk.size_chars, chunk.parent_chunk_id, json.dumps(chunk.contained_symbols),
            ),
        )
        await conn.execute(q.INSERT_CHUNK_FTS, (chunk.chunk_id,))
        
async def persist_refs_only(conn: aiosqlite.Connection, parsed: ParsedFileChunks) -> None:
    """Insert refs for one file's chunks. Call only after ALL files' chunks
    across the repo have been persisted (two-pass), since points_to may
    reference a chunk_id in a file processed later.
    """
    chunk_ids = [c.chunk_id for c in parsed.chunks]
    if chunk_ids:
        sql = q.DELETE_REFS_BY_SOURCE_CHUNK.format(placeholders=_placeholders(chunk_ids))
        await conn.execute(sql, chunk_ids)

    for chunk in parsed.chunks:
        for ref in chunk.references:
            await conn.execute(
                q.INSERT_REF,
                (chunk.chunk_id, ref.text, ref.kind, ref.points_to, ref.start_byte, ref.end_byte, ref.status),
            )


async def persist_skipped(conn: aiosqlite.Connection, result: RepositoryChunkResult) -> None:
    for s in result.skipped:
        await conn.execute(q.UPSERT_SKIPPED_FILE, (s.file_path, s.reason))


async def persist_repository(
    conn: aiosqlite.Connection,
    result: RepositoryChunkResult,
    file_contents: dict[str, bytes],
) -> None:
    """Full repo persist: two passes (all chunks, then all refs) so
    cross-file points_to references resolve correctly regardless of
    file processing order.

    NOTE: aiosqlite.Connection does not support `async with conn:` as a
    transaction wrapper the way asyncpg does — that re-triggers connection
    setup and crashes. Use explicit commit/rollback instead.
    """
    try:
        for parsed in result.files:
            await persist_chunks_only(conn, parsed, file_contents[parsed.file_path])
        for parsed in result.files:
            await persist_refs_only(conn, parsed)
        await persist_skipped(conn, result)
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise


async def persist_single_file(
    conn: aiosqlite.Connection,
    parsed: ParsedFileChunks,
    file_content: bytes,
) -> None:
    """Incremental re-index of ONE file, for the file-watcher path.
    Marks referencing refs stale rather than eagerly re-resolving them
    repo-wide (Decision #15 — lazy cross-file ref resolution).
    """
    try:
        await persist_chunks_only(conn, parsed, file_content)
        await persist_refs_only(conn, parsed)
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise


# --- Read queries, returning typed dataclasses -----------------------------

async def get_chunk(conn: aiosqlite.Connection, chunk_id: str) -> ChunkRow | None:
    cur = await conn.execute(q.SELECT_CHUNK_BY_ID, (chunk_id,))
    row = await cur.fetchone()
    return ChunkRow.from_row(row) if row else None


async def get_chunks_by_file(conn: aiosqlite.Connection, file_path: str) -> list[ChunkRow]:
    cur = await conn.execute(q.SELECT_CHUNKS_BY_FILE, (file_path,))
    return [ChunkRow.from_row(row) for row in await cur.fetchall()]


async def get_chunk_by_name(conn: aiosqlite.Connection, name: str) -> list[ChunkRow]:
    cur = await conn.execute(q.SELECT_CHUNKS_BY_NAME, (name, name))
    return [ChunkRow.from_row(row) for row in await cur.fetchall()]


async def get_callers(conn: aiosqlite.Connection, chunk_id: str) -> list[CallerRow]:
    """Who references this chunk. Only returns status='local' refs."""
    cur = await conn.execute(q.SELECT_CALLERS, (chunk_id,))
    return [CallerRow.from_row(row) for row in await cur.fetchall()]


async def get_callees(conn: aiosqlite.Connection, chunk_id: str) -> list[RefRow]:
    """What this chunk references. Only returns status='local' refs."""
    cur = await conn.execute(q.SELECT_CALLEES, (chunk_id,))
    return [RefRow.from_row(row) for row in await cur.fetchall()]


async def search_by_name(conn: aiosqlite.Connection, query: str) -> list[dict]:
    cur = await conn.execute(q.SEARCH_CHUNKS_FTS, (query,))
    rows = await cur.fetchall()
    return [{"chunk_id": r["chunk_id"], "name": r["name"], "full_name": r["full_name"]} for r in rows]
