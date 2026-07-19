# Step 3 — Parsing & the Language Registry

**Modules:** `app/ingestion/source_parser.py`, `app/ingestion/languages/__init__.py`, and the four `app/ingestion/languages/{python,go,javascript,typescript}_language.py` modules.

## Language registry (`languages/__init__.py`)
`LANG_HELPERS` maps canonical language names (`"python"`, `"go"`, `"javascript"`, `"typescript"`) to helper modules. At import time, every registered module is checked against `REQUIRED_ATTRS`:
`FILE_EXTENSION, get_language, QUERY, REF_QUERY, unwrap_decorated_definition_node, get_definition_name, get_enclosing_class_name, get_module_index_filename, is_builtin` — missing any raises `ImportError` immediately.

Capture-name constants:
- `DEF_CAPTURES = ("func.def", "class.def", "interface.def")`
- `IMPORT_CAPTURE = "import.stmt"`

## Per-language helper contract
Each language supplies: a tree-sitter `QUERY` (definitions + imports), a `REF_QUERY` (calls + inheritance), `CLASS_NODE_TYPES` (which captured node types become `CLASS_SKELETON` chunks), `FILE_EXTENSION`, and helper functions for name/namespace/enclosing-class extraction.

Optional extras (`get_namespace`, `get_class_skeleton_header/footer`, `get_class_member_stub_info`, `derive_import_bound_name`, `RESOLVES_IMPORT_TO_DIRECTORY`, `PATH_USES_DOTS`, `ALLOWS_SUBMODULE_IMPORTS`) are looked up with `getattr(..., None)`.

| Language   | Extension | Class-like nodes | Notable flags |
|---|---|---|---|
| Python     | `.py`  | `class_definition` | `ALLOWS_SUBMODULE_IMPORTS = True` |
| Go         | `.go`  | *(none)* | `RESOLVES_IMPORT_TO_DIRECTORY=True`, `PATH_USES_DOTS=False` |
| JavaScript | `.js`  | `class_declaration` | — |
| TypeScript | `.ts`  | `class_declaration` | — |

## `CodeParser` (`source_parser.py`)
- `load_languages()` builds one `LanguageConfig` per registered language: compiles grammar, `Parser`, and both `Query` objects.
- `CodeParser.parse_file(file_path, content)`:
  1. Validates file extension is registered.
  2. Parses raw bytes with tree-sitter `Parser`.
  3. Returns `ParsedFile(tree, query, ref_query, language, content)`.

## Output
One `ParsedFile` per source file, carrying parse tree, compiled queries, language name, and raw content bytes.
