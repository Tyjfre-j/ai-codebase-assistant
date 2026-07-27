"""Typed return shapes for storage queries.

Kept separate from app.ingestion.code_chunk's CodeChunk/RefRecord — these
represent DB rows (a subset/reshaping of the ingestion dataclasses, plus
DB-only fields like `stale` and `ref_stale`), not the ingestion pipeline's
in-memory model. Named *Row to make that distinction unambiguous at the
call site.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class ChunkRow:
    chunk_id: str
    full_name: str
    name: str
    file_path: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    language: str
    defined_in_class: str | None
    node_type: str | None
    kind: str
    size_chars: int
    parent_chunk_id: str | None
    contained_symbols: list[str]

    @classmethod
    def from_row(cls, row) -> "ChunkRow":
        return cls(
            chunk_id=row["chunk_id"],
            full_name=row["full_name"],
            name=row["name"],
            file_path=row["file_path"],
            start_byte=row["start_byte"],
            end_byte=row["end_byte"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            language=row["language"],
            defined_in_class=row["defined_in_class"],
            node_type=row["node_type"],
            kind=row["kind"],
            size_chars=row["size_chars"],
            parent_chunk_id=row["parent_chunk_id"],
            contained_symbols=json.loads(row["contained_symbols"]),
        )


@dataclass
class CallerRow:
    """A caller chunk, joined with the staleness of the ref that points to
    the target chunk being looked up (not the caller chunk's own data).
    """
    chunk: ChunkRow
    ref_stale: bool

    @classmethod
    def from_row(cls, row) -> "CallerRow":
        return cls(chunk=ChunkRow.from_row(row), ref_stale=bool(row["ref_stale"]))


@dataclass
class RefRow:
    id: int
    source_chunk_id: str
    text: str
    kind: str
    points_to: str | None
    start_byte: int
    end_byte: int
    status: str
    stale: bool

    @classmethod
    def from_row(cls, row) -> "RefRow":
        return cls(
            id=row["id"],
            source_chunk_id=row["source_chunk_id"],
            text=row["text"],
            kind=row["kind"],
            points_to=row["points_to"],
            start_byte=row["start_byte"],
            end_byte=row["end_byte"],
            status=row["status"],
            stale=bool(row["stale"]),
        )
