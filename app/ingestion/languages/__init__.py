from app.ingestion.languages import (
    go_queries,
    javascript_queries,
    python_queries,
    typescript_queries,
)

LANG_HELPERS = {
    "python": python_queries,
    "go": go_queries,
    "javascript": javascript_queries,
    "typescript": typescript_queries,
}

REQUIRED_ATTRS = ("QUERY", "resolve_definition_node", "resolve_parent_class")

for _lang_name, _module in LANG_HELPERS.items():
    _missing = [attr for attr in REQUIRED_ATTRS if not hasattr(_module, attr)]
    if _missing:
        raise ImportError(f"{_lang_name} language module missing: {_missing}")

DEF_CAPTURES = ("func.def", "class.def", "interface.def")
IMPORT_CAPTURE = "import.stmt"