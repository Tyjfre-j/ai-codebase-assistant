"""All raw SQL for the storage layer, kept out of db.py so query text is easy
to find, diff, and review independently of the Python logic around it.

Naming convention: UPPER_SNAKE_CASE, grouped by table/purpose, matching what
each query does rather than which function calls it.
"""

UPSERT_FILE = """
INSERT INTO files (file_path, content_hash, language) VALUES (?, ?, ?)
ON CONFLICT(file_path) DO UPDATE SET
    content_hash = excluded.content_hash,
    language = excluded.language,
    indexed_at = datetime('now')
"""

SELECT_CHUNK_IDS_BY_FILE = "SELECT chunk_id FROM chunks WHERE file_path = ?"

DELETE_CHUNKS_BY_FILE = "DELETE FROM chunks WHERE file_path = ?"

# Delete refs whose SOURCE chunk is in the given file — must run BEFORE
# deleting chunks to avoid FK constraint violations.
DELETE_REFS_BY_FILE = """
DELETE FROM refs WHERE source_chunk_id IN (
    SELECT chunk_id FROM chunks WHERE file_path = ?
)
"""

INSERT_CHUNK = """
INSERT INTO chunks (
    chunk_id, full_name, name, file_path,
    start_byte, end_byte, start_line, end_line,
    language, defined_in_class, node_type, kind,
    size_chars, parent_chunk_id, contained_symbols
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""

INSERT_CHUNK_FTS = """
INSERT INTO chunks_fts (rowid, chunk_id, name, full_name)
SELECT rowid, chunk_id, name, full_name FROM chunks WHERE chunk_id = ?
"""

DELETE_REFS_BY_SOURCE_CHUNK = "DELETE FROM refs WHERE source_chunk_id IN ({placeholders})"

MARK_REFS_STALE_BY_TARGET = "UPDATE refs SET stale = 1 WHERE points_to IN ({placeholders})"

DELETE_CHUNKS_FTS_BY_ID = "DELETE FROM chunks_fts WHERE chunk_id IN ({placeholders})"

INSERT_REF = """
INSERT INTO refs (source_chunk_id, text, kind, points_to, start_byte, end_byte, status, stale)
VALUES (?,?,?,?,?,?,?,0)
"""

UPSERT_SKIPPED_FILE = """
INSERT INTO skipped_files (file_path, reason) VALUES (?, ?)
ON CONFLICT(file_path) DO UPDATE SET reason = excluded.reason, indexed_at = datetime('now')
"""

SELECT_CHUNK_BY_ID = "SELECT * FROM chunks WHERE chunk_id = ?"

SELECT_CHUNKS_BY_FILE = "SELECT * FROM chunks WHERE file_path = ? ORDER BY start_line"

SELECT_CHUNKS_BY_NAME = "SELECT * FROM chunks WHERE name = ? OR full_name = ?"

SELECT_CALLERS = """
SELECT c.*, r.stale as ref_stale
FROM refs r
JOIN chunks c ON c.chunk_id = r.source_chunk_id
WHERE r.points_to = ? AND r.status = 'local'
"""

SELECT_CALLEES = """
SELECT * FROM refs
WHERE source_chunk_id = ? AND status = 'local'
"""

SEARCH_CHUNKS_FTS = """
SELECT chunk_id, name, full_name FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank
"""

SELECT_FILE_HASH = "SELECT content_hash FROM files WHERE file_path = ?"