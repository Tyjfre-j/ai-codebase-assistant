-- SQLite schema for chunk + ref persistence
-- Chunk code is NOT stored here; re-read from source on demand via start_byte/end_byte

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS files (
    file_path TEXT PRIMARY KEY,
    content_hash TEXT,
    language TEXT,
    indexed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    full_name TEXT,
    name TEXT,
    file_path TEXT NOT NULL,
    start_byte INTEGER,
    end_byte INTEGER,
    start_line INTEGER,
    end_line INTEGER,
    language TEXT,
    defined_in_class TEXT,
    node_type TEXT,
    kind TEXT NOT NULL,
    size_chars INTEGER,
    parent_chunk_id TEXT,
    contained_symbols TEXT,
    FOREIGN KEY (file_path) REFERENCES files(file_path)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id,
    name,
    full_name
);

CREATE TABLE IF NOT EXISTS refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_chunk_id TEXT NOT NULL,
    text TEXT NOT NULL,
    kind TEXT NOT NULL,
    points_to TEXT,
    start_byte INTEGER,
    end_byte INTEGER,
    status TEXT NOT NULL,
    stale INTEGER DEFAULT 0,
    FOREIGN KEY (source_chunk_id) REFERENCES chunks(chunk_id)
);

CREATE TABLE IF NOT EXISTS skipped_files (
    file_path TEXT PRIMARY KEY,
    reason TEXT,
    indexed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for traversal queries
CREATE INDEX IF NOT EXISTS idx_chunks_file_path ON chunks(file_path);
CREATE INDEX IF NOT EXISTS idx_chunks_name ON chunks(name);
CREATE INDEX IF NOT EXISTS idx_chunks_full_name ON chunks(full_name);
CREATE INDEX IF NOT EXISTS idx_refs_source_chunk_id ON refs(source_chunk_id);
CREATE INDEX IF NOT EXISTS idx_refs_points_to ON refs(points_to);
CREATE INDEX IF NOT EXISTS idx_refs_status ON refs(status);
