import pytest

from app.ingestion.chunking.query_captures import run_captures
from app.ingestion.languages import DEF_CAPTURES, LANG_HELPERS
from app.ingestion.source_parser import CodeParser

parser = CodeParser()


def _find_def_by_name(parsed, captures, name):
    helpers = LANG_HELPERS[parsed.language]
    for cap in DEF_CAPTURES:
        for node in captures.get(cap, []):
            if helpers.get_definition_name(node, parsed.content) == name:
                return node
    raise AssertionError(f"no definition named {name!r} found in captures")

def _resolve(fake_path, source, def_name):
    parsed = parser.parse_file(fake_path, source.encode("utf-8"))
    captures = run_captures(parsed)
    node = _find_def_by_name(parsed, captures, def_name)
    helpers = LANG_HELPERS[parsed.language]
    return helpers.get_enclosing_class_name(node, captures, parsed.content)


PYTHON_CASES = [
    ("class Foo:\n    def bar(self): pass", "bar", "Foo"),
    ("def outer():\n    def inner(): pass", "inner", None),
    ("class Foo:\n    class Bar:\n        def baz(self): pass", "baz", "Bar"),
    ("class Foo:\n    @staticmethod\n    def bar(): pass", "bar", "Foo"),
]


@pytest.mark.parametrize("source, def_name, expected", PYTHON_CASES)
def test_python_resolve_parent_class(source, def_name, expected):
    assert _resolve("case.py", source, def_name) == expected


GO_CASES = [
    ("package main\ntype Foo struct{}\nfunc (f *Foo) Bar() {}", "Bar", "Foo"),
    ("package main\ntype Foo struct{}\nfunc (f Foo) Baz() {}", "Baz", "Foo"),
    ("package main\nfunc Standalone() {}", "Standalone", None),
]


@pytest.mark.parametrize("source, def_name, expected", GO_CASES)
def test_go_resolve_parent_class(source, def_name, expected):
    assert _resolve("case.go", source, def_name) == expected


JS_CASES = [
    ("class Foo { bar() {} }", "bar", "Foo"),
    ("const obj = { bar() {} };", "bar", None),
    ("class Foo { bar = () => {} }", "bar", "Foo"),
]


@pytest.mark.parametrize("source, def_name, expected", JS_CASES)
def test_javascript_resolve_parent_class(source, def_name, expected):
    assert _resolve("case.js", source, def_name) == expected


TS_CASES = [
    ("class Foo { bar(): void {} }", "bar", "Foo"),
    ("class Foo { bar = (): void => {} }", "bar", "Foo"),
    ("class Foo implements Bar { baz(): number { return 1; } }", "baz", "Foo"),
]


@pytest.mark.parametrize("source, def_name, expected", TS_CASES)
def test_typescript_resolve_parent_class(source, def_name, expected):
    assert _resolve("case.ts", source, def_name) == expected