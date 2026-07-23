#!/usr/bin/env python3
"""Diagnostic: check what node types tree-sitter captures for decorated definitions."""
from tree_sitter import QueryCursor
from app.ingestion.source_parser import CodeParser
from app.ingestion.languages import LANG_HELPERS


def diagnose(code: str, label: str):
    print(f"\n=== {label} ===")
    parser = CodeParser()
    content = code.encode("utf-8")
    parsed = parser.parse_file("/fake/path.py", content)

    cursor = QueryCursor(parsed.query)
    captures = cursor.captures(parsed.tree.root_node)

    print(f"  All capture names: {list(captures.keys())}")
    for capture_name, nodes in captures.items():
        print(f"  Capture '{capture_name}' ({len(nodes)} nodes):")
        for node in nodes:
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node else "<no name>"
            print(f"    type={node.type}, name={name}, bytes=({node.start_byte},{node.end_byte})")
            if node.parent:
                print(f"      parent: type={node.parent.type}, bytes=({node.parent.start_byte},{node.parent.end_byte})")

    # Also show what unwrap_decorated_definition_node does
    helper = LANG_HELPERS["python"]
    unwrap = getattr(helper, "unwrap_decorated_definition_node", None)
    if unwrap:
        print(f"  unwrap_decorated_definition_node results:")
        for capture_name, nodes in captures.items():
            if capture_name not in ("func.def", "class.def"):
                continue
            for node in nodes:
                name_node = node.child_by_field_name("name")
                name = name_node.text.decode("utf-8") if name_node else "<no name>"
                unwrapped = unwrap(node)
                print(f"    {capture_name} {name}: {node.type} -> {unwrapped.type} (bytes {unwrapped.start_byte}-{unwrapped.end_byte})")


if __name__ == "__main__":
    # Test 1: Plain function
    diagnose("""
def foo():
    pass
""", "Plain function")

    # Test 2: Decorated function
    diagnose("""
@decorator(arg=call_me())
def foo():
    pass
""", "Decorated function")

    # Test 3: Plain class
    diagnose("""
class Foo:
    pass
""", "Plain class")

    # Test 4: Decorated class
    diagnose("""
@decorator(arg=call_me())
class Foo:
    pass
""", "Decorated class")

    # Test 5: Class with inheritance
    diagnose("""
class Foo(Base):
    pass
""", "Class with inheritance")
