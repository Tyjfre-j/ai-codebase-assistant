"""Temporary CLI entrypoint to run the full ingestion pipeline against a repo path."""
import sys

from app.ingestion.repo_chunker import chunk_repository
from app.ingestion.refs.resolver import resolve_all_chunk_references


def run(root: str) -> None:
    parsed_chunks_list = chunk_repository(root)
    resolve_all_chunk_references(parsed_chunks_list)

    total_chunks = sum(len(pc.chunks) for pc in parsed_chunks_list)
    total_refs = sum(len(c.references) for pc in parsed_chunks_list for c in pc.chunks)
    resolved = sum(
        1 for pc in parsed_chunks_list for c in pc.chunks for ref in c.references
        if ref.status == "local"
    )
    unresolved = total_refs - resolved

    print(f"Files parsed: {len(parsed_chunks_list)}")
    print(f"Total chunks: {total_chunks}")
    print(f"Total refs: {total_refs}")
    print(f"Resolved (local): {resolved}")
    print(f"Unresolved: {unresolved}")

    # Print a few examples so you can sanity check by eye
    print("\n--- sample resolved refs ---")
    count = 0
    for pc in parsed_chunks_list:
        for c in pc.chunks:
            for ref in c.references:
                if ref.status == "local" and count < 10:
                    print(f"{pc.file_path}:{c.name} -> {ref.text} -> chunk_id={ref.points_to}")
                    count += 1

    print("\n--- sample UNRESOLVED refs ---")
    count = 0
    for pc in parsed_chunks_list:
        for c in pc.chunks:
            for ref in c.references:
                if ref.status == "unresolved" and count < 20:
                    print(f"{pc.file_path}:{c.name} -> {ref.text}")
                    count += 1

    print("\n--- unresolved breakdown ---")
    own_symbol_names = {c.name for pc in parsed_chunks_list for c in pc.chunks if c.kind == "definition"}
    own_qualified_names = {c.full_name for pc in parsed_chunks_list for c in pc.chunks if c.kind == "definition"}

    suspicious = []
    for pc in parsed_chunks_list:
        for c in pc.chunks:
            for ref in c.references:
                if ref.status != "unresolved":
                    continue
                root = ref.text.split(".")[0]
                # Suspicious: the bare root or the raw_name itself IS a name we define
                # somewhere in the codebase, yet it still failed to resolve.
                if root in own_symbol_names or ref.text in own_qualified_names:
                    suspicious.append((pc.file_path, c.name, ref.text))

    print(f"Unresolved refs whose root matches a KNOWN symbol name: {len(suspicious)}")
    for entry in suspicious[:30]:
        print(entry)
        
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run_pipeline.py <repo_path>")
        sys.exit(1)
    run(sys.argv[1])