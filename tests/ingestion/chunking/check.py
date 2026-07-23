#!/usr/bin/env python3
"""Diagnostic: Check what class skeleton actually contains for methods."""
from app.ingestion.chunking.chunk_pipeline import chunk_file
from app.ingestion.code_chunk import ChunkKind
from app.ingestion.source_parser import CodeParser


def diagnose(code: str, label: str, budget: int = 500):
    print(f"\n=== {label} ===")
    parser = CodeParser()
    content = code.encode("utf-8")
    parsed = parser.parse_file("/fake/path.py", content)

    chunks, import_text, import_ranges, captures = chunk_file("/fake/path.py", parsed, budget=budget)

    print(f"All chunks:")
    for c in chunks:
        print(f"  {c.kind:20s} | {c.name:15s} | size={c.size_chars}")

    sk = [c for c in chunks if c.kind == ChunkKind.DEFINITION_SKELETON]
    if sk:
        print(f"\nClass skeleton code:")
        print("-" * 40)
        print(sk[0].code)
        print("-" * 40)
    else:
        print("No DEFINITION_SKELETON found")


# Test 1: Class with methods (should skeleton show method stubs?)
body = "\n".join([f"    x = {i}" for i in range(200)])
code1 = f"""
class Outer:
{body}
    def method(self, x):
        pass

    def other(self):
        pass
"""
diagnose(code1, "Class with methods")

# Test 2: Class with decorated methods
code2 = f"""
class Outer:
{body}
    @decorator
    def method(self, x):
        pass

    @property
    def name(self):
        return "foo"
"""
diagnose(code2, "Class with decorated methods")

# Test 3: Class with nested class
code3 = f"""
class Outer:
{body}
    class Inner:
        def method(self):
            pass
"""
diagnose(code3, "Class with nested class")

# Test 4: Small class (should be DEFINITION, not skeleton)
code4 = """
class Small:
    def method(self):
        pass
"""
diagnose(code4, "Small class (under budget)", budget=4000)
