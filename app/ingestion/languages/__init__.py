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

REQUIRED_ATTRS = (
    "QUERY",
    "REF_QUERY",
    "FILE_EXTENSION",
    "get_language",
    "get_decoration_of_definition_node",
    "get_node_name",
    "get_node_body",
    "get_actual_definition_node",
    "get_actual_definition_type",
    "get_definition_name",
    "get_parent_class_name",
    "get_ancestor_namespace",
    "get_member_stub_info",
    "get_class_header",
    "get_class_footer",
    "is_builtin",
)

for _language_name, _language_module in LANG_HELPERS.items():
    _missing_attrs = [
        attr for attr in REQUIRED_ATTRS if not hasattr(_language_module, attr)
    ]
    if _missing_attrs:
        raise ImportError(f"{_language_name} language module missing: {_missing_attrs}")

FUNC_DEF_CAPTURE = "func.def"
CLASS_DEF_CAPTURE = "class.def"
INTERFACE_DEF_CAPTURE = "interface.def"

DEF_CAPTURES = (FUNC_DEF_CAPTURE, CLASS_DEF_CAPTURE, INTERFACE_DEF_CAPTURE)
IMPORT_CAPTURE = "import.stmt"