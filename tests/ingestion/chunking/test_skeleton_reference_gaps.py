import pytest
from tree_sitter import Node, QueryCursor

from app.ingestion.chunking.chunk_factory import (
    build_skeleton_chunk,
    build_file_skeleton_chunk,
    build_definition_chunk,
    _filter_out_nested_refs,
)
from app.ingestion.code_chunk import ChunkKind, RefKind
from app.ingestion.source_parser import CodeParser, ParsedFile
from app.ingestion.languages import LANG_HELPERS
from app.ingestion.chunking.query_captures import run_captures


def _parse_and_capture(code: str, language: str = "python") -> tuple[ParsedFile, dict, set, set]:
    """Parse code and return (parsed, captures_dict, definition_ids, import_ids)."""
    parser = CodeParser()
    content = code.encode("utf-8")
    parsed = parser.parse_file("/fake/path.py", content)

    captures_dict = run_captures(parsed)

    definition_ids = set()
    import_ids = set()

    for name, nodes in captures_dict.items():
        if name in ("func.def", "class.def", "interface.def"):
            for node in nodes:
                definition_ids.add(node.id)
        if name == "import.stmt":
            for node in nodes:
                import_ids.add(node.id)

    return parsed, captures_dict, definition_ids, import_ids


def _find_node_by_capture(captures, capture_name, target_name):
    """Find a node by exact capture name and node name."""
    from app.ingestion.languages import LANG_HELPERS
    helpers = LANG_HELPERS["python"]
    for node in captures.get(capture_name, []):
        name_node = helpers.get_node_name(node)
        if name_node and name_node.text.decode("utf-8") == target_name:
            return node
    return None






def test_oversized_function_skeleton_captures_default_param_call():
    """An oversized function with a call in default param value keeps that ref in skeleton."""
    body = "\n".join([f"    x = {i}" for i in range(100)])
    code = f"""
def compute_default():
    return 42

def foo(x=compute_default()):
{body}
"""
    parsed, captures, definition_ids, import_ids = _parse_and_capture(code)

    func_node = _find_node_by_capture(captures, "func.def", "foo")
    assert func_node is not None, f"Could not find foo function node. Captures: {list(captures.keys())}"


    sk = build_skeleton_chunk(func_node, "/fake/path.py", parsed, captures, definition_ids)

    call_refs = [r for r in sk.references if r.kind == RefKind.CALL]
    texts = [r.text for r in call_refs]
    assert "compute_default" in texts, f"Expected compute_default in refs, got {texts}"


def test_function_skeleton_captures_decorator_call():
    """A call inside a decorator argument should appear in FUNCTION_SKELETON refs."""
    body = "\n".join([f"    x = {i}" for i in range(100)])
    code = f"""
def my_decorator(arg):
    return lambda f: f

@my_decorator(arg=compute_default())
def foo():
{body}
"""
    parsed, captures, definition_ids, import_ids = _parse_and_capture(code)

    func_node = _find_node_by_capture(captures, "func.def", "foo")
    assert func_node is not None, f"Could not find foo function node. Captures: {list(captures.keys())}"


    sk = build_skeleton_chunk(func_node, "/fake/path.py", parsed, captures, definition_ids)

    call_refs = [r for r in sk.references if r.kind == RefKind.CALL]
    texts = [r.text for r in call_refs]
    assert "compute_default" in texts, f"Expected compute_default in refs, got {texts}"
    assert "my_decorator" in texts, f"Expected my_decorator in refs, got {texts}"


def test_class_skeleton_captures_decorator_call():
    """A call inside a class decorator argument should appear in CLASS_SKELETON refs."""
    body = "\n".join([f"    x = {i}" for i in range(100)])
    code = f"""
def register(cls):
    return cls

@register(factory=make_default())
class BigClass:
{body}
"""
    parsed, captures, definition_ids, import_ids = _parse_and_capture(code)

    class_node = _find_node_by_capture(captures, "class.def", "BigClass")
    assert class_node is not None, f"Could not find BigClass node. Captures: {list(captures.keys())}"


    sk = build_skeleton_chunk(class_node, "/fake/path.py", parsed, captures, definition_ids)

    call_refs = [r for r in sk.references if r.kind == RefKind.CALL]
    texts = [r.text for r in call_refs]
    assert "make_default" in texts, f"Expected make_default in refs, got {texts}"
    assert "register" in texts, f"Expected register in refs, got {texts}"


def test_no_double_counting_between_skeleton_and_nested_def():
    """A call inside a nested method should ONLY appear in that method's chunk, not the parent skeleton."""
    body = "\n".join([f"    x = {i}" for i in range(100)])
    code = f"""
def helper():
    pass

class BigClass:
{body}
    def method(self):
        helper()
"""
    parsed, captures, definition_ids, import_ids = _parse_and_capture(code)

    class_node = _find_node_by_capture(captures, "class.def", "BigClass")
    assert class_node is not None, f"Could not find BigClass node. Captures: {list(captures.keys())}"


    sk = build_skeleton_chunk(class_node, "/fake/path.py", parsed, captures, definition_ids)

    method_node = _find_node_by_capture(captures, "func.def", "method")
    assert method_node is not None, f"Could not find method node. Captures: {list(captures.keys())}"

    method_chunk = build_definition_chunk(method_node, "/fake/path.py", parsed, captures, definition_ids)

    sk_call_texts = [r.text for r in sk.references if r.kind == RefKind.CALL]
    method_call_texts = [r.text for r in method_chunk.references if r.kind == RefKind.CALL]

    assert "helper" in method_call_texts, f"Expected helper in method refs, got {method_call_texts}"
    assert "helper" not in sk_call_texts, f"helper should NOT be in skeleton refs, got {sk_call_texts}"


def test_file_skeleton_no_double_counting():
    """Top-level code refs go to FILE_SKELETON; nested def refs don't leak there."""
    code = """
def helper():
    pass

def top_level():
    helper()

x = 1
"""
    parsed, captures, definition_ids, import_ids = _parse_and_capture(code)

    file_sk = build_file_skeleton_chunk(
        parsed.tree.root_node, "/fake/path.py", parsed, definition_ids, import_ids
    )

    func_node = _find_node_by_capture(captures, "func.def", "top_level")
    assert func_node is not None, f"Could not find top_level node. Captures: {list(captures.keys())}"

    func_chunk = build_definition_chunk(func_node, "/fake/path.py", parsed, captures, definition_ids)

    sk_call_texts = [r.text for r in file_sk.references if r.kind == RefKind.CALL]
    func_call_texts = [r.text for r in func_chunk.references if r.kind == RefKind.CALL]

    assert "helper" in func_call_texts
    assert "helper" not in sk_call_texts, f"helper should NOT leak to file skeleton, got {sk_call_texts}"


def test_class_skeleton_captures_inheritance():
    """Base class references should always appear in CLASS_SKELETON."""
    body = "\n".join([f"    x = {i}" for i in range(100)])
    code = f"""
class Base:
    pass

class BigClass(Base):
{body}
"""
    parsed, captures, definition_ids, import_ids = _parse_and_capture(code)

    class_node = _find_node_by_capture(captures, "class.def", "BigClass")
    assert class_node is not None, f"Could not find BigClass node. Captures: {list(captures.keys())}"
    sk = build_skeleton_chunk(class_node, "/fake/path.py", parsed, captures, definition_ids)

    inh_refs = [r for r in sk.references if r.kind == RefKind.INHERITANCE]
    texts = [r.text for r in inh_refs]
    assert "Base" in texts, f"Expected Base in inheritance refs, got {texts}"
