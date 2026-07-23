"""Language query/helper registry used by the ingestion parser and chunker."""

from typing import cast

from app.ingestion.languages import (
    go_language,
    javascript_language,
    python_language,
    typescript_language,
)
from app.ingestion.languages.protocol import LanguageModule

LANG_HELPERS: dict[str, LanguageModule] = {
    "python": cast(LanguageModule, python_language),
    "typescript": cast(LanguageModule, typescript_language),
    "javascript": cast(LanguageModule, javascript_language),
    "go": cast(LanguageModule, go_language),
}

_REQUIRED_ATTRS = (
    "QUERY",
    "REF_QUERY",
    "FILE_EXTENSION",
    "ALLOWS_SUBMODULE_IMPORTS",
    "SELF_REFERENCE_NAMES",
    "DECORATED_DEFINITION_NODE_TYPES",
    "FUNCTION_DEFINITION_NODE_TYPES",
    "CLASS_DEFINITION_NODE_TYPES",
    "INTERFACE_DEFINITION_NODE_TYPES",
)

_REQUIRED_CALLABLES = (
    "get_language",
    "get_decoration_of_definition_node",
    "get_node_name",
    "get_node_body",
    "get_actual_definition_node",
    "get_actual_definition_type",
    "get_definition_name",
    "get_enclosing_class_name",
    "get_ancestor_namespace",
    "get_signature_text",
    "get_class_footer",
    "get_package_index_filename",
    "is_builtin",
)

for _language_name, _language_module in LANG_HELPERS.items():
    _missing_attrs = [
        attr for attr in _REQUIRED_ATTRS if not hasattr(_language_module, attr)
    ]
    _missing_callables = [
        attr for attr in _REQUIRED_CALLABLES
        if not callable(getattr(_language_module, attr, None))
    ]
    if _missing_attrs or _missing_callables:
        _parts = []
        if _missing_attrs:
            _parts.append(f"missing attributes: {_missing_attrs}")
        if _missing_callables:
            _parts.append(f"missing/not-callable: {_missing_callables}")
        raise ImportError(f"{_language_name} language module – {'; '.join(_parts)}")

FUNC_DEF_CAPTURE = "func.def"
CLASS_DEF_CAPTURE = "class.def"
INTERFACE_DEF_CAPTURE = "interface.def"

DEF_CAPTURES = (FUNC_DEF_CAPTURE, CLASS_DEF_CAPTURE, INTERFACE_DEF_CAPTURE)
IMPORT_CAPTURE = "import.stmt"