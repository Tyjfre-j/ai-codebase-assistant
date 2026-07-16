# Step 7 — Splitting Leftovers into Imports & Budgeted Chunks

**Module:** `app/ingestion/chunking/leftover_chunks.py`
**Entry point:** `group_leftovers(leftover_groups, captures, file_path, parsed, budget)`

## Purpose
Each `LEFTOVER` candidate from Step 5 is a raw bundle of adjacent non-
definition nodes — this could include import statements mixed in with
module-level code. This stage separates the two concerns: pull import
statements out into their own metadata (for Step 10), and pack whatever
remains into `CodeChunk`s that respect the size `budget`.

## Algorithm, per leftover group
1. Identify which nodes in the group are import statements
   (`node.id in import_ids`, from the `import.stmt` capture).
2. Walk the group in order, splitting it into `segments`: a segment is a
   maximal run of *non-import* nodes; hitting an import node always closes
   the current segment (without including the import itself in any
   segment) and starts a new one on the next non-import node.
3. Pack segments into `chunk_buffer`s greedily: keep adding segments to the
   current buffer while its running byte-size stays within `budget`; once
   adding the next segment would exceed it, flush the current buffer as one
   `build_leftover_code_chunk` call and start a new buffer. A single
   segment larger than the whole budget still becomes its own
   (over-budget) chunk rather than being split further.
4. All import nodes across every group are collected into one `imports`
   list, in the order encountered.

## Output
- `leftover_chunks: list[CodeChunk]` — budgeted, import-free code chunks.
- `import_text: str` — every import statement's source text, joined with
  `"\n"`, in document order.
- `import_ranges: list[tuple[start_byte, end_byte]]` — one entry per import
  statement, in the same order as `import_text`.

`import_text`/`import_ranges` are returned up through `chunk_file` (Step 8)
purely as metadata on `ParsedFileChunks` — they are not, on their own, what
resolves an import to a chunk; that's Steps 10–11, which re-derive bindings
from the *captures* dict directly rather than from this text/ranges output.
