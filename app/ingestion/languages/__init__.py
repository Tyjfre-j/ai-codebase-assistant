"""Language query/helper registry used by the ingestion parser and chunker."""

from app.ingestion.languages import (
    go_language,
    javascript_language,
    python_language,
    typescript_language,
)

LANG_HELPERS = {
    "python": python_language,
    "go": go_language,
    "javascript": javascript_language,
    "typescript": typescript_language,
}

REQUIRED_ATTRS = ("QUERY", "resolve_definition_node", "resolve_parent_class")

for _language_name, _language_module in LANG_HELPERS.items():
    _missing_attrs = [
        attr for attr in REQUIRED_ATTRS if not hasattr(_language_module, attr)
    ]
    if _missing_attrs:
        raise ImportError(f"{_language_name} language module missing: {_missing_attrs}")

DEF_CAPTURES = ("func.def", "class.def", "interface.def")
IMPORT_CAPTURE = "import.stmt"
