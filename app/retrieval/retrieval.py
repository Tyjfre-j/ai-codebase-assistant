"""Retrieval layer: grep (lexical) + resolved reference graph (structural),
merged into single, ranked, code-bearing responses for MCP tools.

Design per the project plan:
  - Structural graph lookups (definition/callers/callees) are the primary,
    precise path — resolved at ingestion time, no guessing.
  - grep is the fallback / complement for anything not captured as a
    resolved chunk/ref (e.g. a raw string, a config key, an unresolved name).
  - Chunk code is NEVER stored in the DB — always re-read from the source
    file on demand via start_byte/end_byte (Decision #3). This means the
    indexed repo's root path must be known and current at query time.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from app.storage.db import (
    get_callees,
    get_callers,
    get_chunk,
    get_chunk_by_name,
    get_chunks_by_file,
)
from app.storage.models import CallerRow, ChunkRow


@dataclass
class CodeResult:
    chunk_id: str
    name: str
    full_name: str
    file_path: str
    start_line: int
    end_line: int
    kind: str
    code: str
    source: str  # "structural" | "grep"
    stale: bool = False


@dataclass
class RetrievalContext:
    """Everything retrieval needs: an open DB connection and the repo's
    current root path on disk (so code can be sliced from source).
    """
    conn: aiosqlite.Connection
    repo_root: Path


def _read_chunk_code(repo_root: Path, file_path: str, start_byte: int, end_byte: int) -> str:
    full_path = repo_root / file_path
    with open(full_path, "rb") as f:
        f.seek(start_byte)
        raw = f.read(end_byte - start_byte)
    return raw.decode("utf-8", errors="replace")


def _row_to_result(ctx: RetrievalContext, row: ChunkRow, source: str, stale: bool = False) -> CodeResult:
    code = _read_chunk_code(ctx.repo_root, row.file_path, row.start_byte, row.end_byte)
    return CodeResult(
        chunk_id=row.chunk_id,
        name=row.name,
        full_name=row.full_name,
        file_path=row.file_path,
        start_line=row.start_line,
        end_line=row.end_line,
        kind=row.kind,
        code=code,
        source=source,
        stale=stale,
    )


# --- Structural (SQL graph) lookups -----------------------------------------

async def get_definition(ctx: RetrievalContext, symbol_name: str) -> list[CodeResult]:
    """Exact + qualified-name match against the chunk table."""
    rows = await get_chunk_by_name(ctx.conn, symbol_name)
    return [_row_to_result(ctx, row, source="structural") for row in rows]


async def find_callers(ctx: RetrievalContext, symbol_name: str) -> list[CodeResult]:
    """Resolve the symbol to its chunk(s), then find every LOCAL ref pointing at it.
    External/builtin refs are excluded — they don't map back to a caller chunk.
    """
    target_chunks = await get_chunk_by_name(ctx.conn, symbol_name)
    results: list[CodeResult] = []
    seen_chunk_ids: set[str] = set()
    for target in target_chunks:
        caller_rows = await get_callers(ctx.conn, target.chunk_id)
        for caller in caller_rows:
            if caller.chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(caller.chunk.chunk_id)
            results.append(_row_to_result(ctx, caller.chunk, source="structural", stale=caller.ref_stale))
    return results


async def find_callees(ctx: RetrievalContext, symbol_name: str) -> list[CodeResult]:
    """What does this symbol call? Returns resolved LOCAL callees as chunks.
    Unresolved/external refs are dropped — there's no chunk to slice code from.
    """
    target_chunks = await get_chunk_by_name(ctx.conn, symbol_name)
    results: list[CodeResult] = []
    seen_chunk_ids: set[str] = set()
    for target in target_chunks:
        ref_rows = await get_callees(ctx.conn, target.chunk_id)
        for ref in ref_rows:
            if not ref.points_to:
                continue
            if ref.points_to in seen_chunk_ids:
                continue
            seen_chunk_ids.add(ref.points_to)
            callee_row = await get_chunk(ctx.conn, ref.points_to)
            if callee_row:
                results.append(_row_to_result(ctx, callee_row, source="structural", stale=ref.stale))
    return results


# --- Lexical (grep) fallback ------------------------------------------------

def grep_search(repo_root: Path, pattern: str, max_results: int = 20) -> list[dict]:
    """Ripgrep-based text search over the repo, for anything the structural
    graph doesn't capture (raw strings, config keys, comments, unresolved
    names). Requires `rg` on PATH.
    """
    if shutil.which("rg") is None:
        raise RuntimeError("ripgrep ('rg') not found on PATH — required for grep_search")

    proc = subprocess.run(
        ["rg", "--json", "--max-count", str(max_results), pattern, str(repo_root)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    matches = []
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "match":
            continue
        data = event["data"]
        matches.append(
            {
                "file_path": str(Path(data["path"]["text"]).relative_to(repo_root)),
                "line_number": data["line_number"],
                "line_text": data["lines"]["text"].rstrip("\n"),
            }
        )
        if len(matches) >= max_results:
            break
    return matches


# --- Merged retrieval (what the MCP tool actually calls) --------------------

async def search(ctx: RetrievalContext, query: str, max_results: int = 20) -> dict:
    """Combine structural (definition + name match) and grep results into one
    ranked response. Structural hits are more precise and are ranked first;
    grep fills in anything structural search missed (raw strings, comments,
    unresolved names, config values).
    """
    structural = await get_definition(ctx, query)

    # run grep in a thread since it shells out and blocks
    grep_hits = await asyncio.to_thread(grep_search, ctx.repo_root, query, max_results)

    # drop grep hits that land on a line already covered by a structural result,
    # so the same function definition doesn't show up twice
    structural_lines = {(r.file_path, ln) for r in structural for ln in range(r.start_line, r.end_line + 1)}
    grep_hits = [h for h in grep_hits if (h["file_path"], h["line_number"]) not in structural_lines]

    return {
        "query": query,
        "structural_results": [r.__dict__ for r in structural],
        "grep_results": grep_hits,
    }
