# Step 3 — Parsing & the Language Registry

**Modules:** `app/ingestion/source_parser.py`,
`app/ingestion/languages/__init__.py`, and the four
`app/ingestion/languages/{python,go,javascript,typescript}_language.py` modules.

## Language registry (`languages/__init__.py`)
`LANG_HELPERS` maps a canonical language name (`"python"`, `"go"`,
`"javascript"`, `"typescript"`) to its helper module. At import time, every
registered module is checked against `REQUIRED_ATTRS`:
`FILE_EXTENSION, get_language, QUERY, REF_QUERY,
unwrap_decorated_definition_node, get_definition_name,
get_enclosing_class_name, get_module_index_filename, is_builtin` — missing
any of these raises `ImportError` at import time, so a malformed language
module fails loudly and immediately rather than at first use.

Also defines the two capture-name constants shared by the whole pipeline:
- `DEF_CAPTURES = ("func.def", "class.def", "interface.def")`
- `IMPORT_CAPTURE = "import.stmt"`

## Per-language helper contract
Each language module supplies, at minimum: a tree-sitter `QUERY` (definitions
+ imports), a `REF_QUERY` (calls + inheritance), `CLASS_NODE_TYPES` (which
captured node types should become `CLASS_SKELETON` chunks instead of full
`DEFINITION` chunks), a `FILE_EXTENSION`, and helper functions to pull a
name/namespace/enclosing-class out of a definition node. Optional extras
(`get_namespace`, `get_class_skeleton_header/footer`,
`get_class_member_stub_info`, `derive_import_bound_name`,
`RESOLVES_IMPORT_TO_DIRECTORY`, `PATH_USES_DOTS`, `ALLOWS_SUBMODULE_IMPORTS`)
are looked up with `getattr(..., None)` / `getattr(..., default)` at call
sites, so each language only implements what its grammar actually needs.

| Language   | Extension | Class-like nodes treated as skeletons | Notable flags |
|---|---|---|---|
| Python     | `.py`  | `class_definition` | `ALLOWS_SUBMODULE_IMPORTS = True` |
| Go         | `.go`  | *(none — see gaps)* | `RESOLVES_IMPORT_TO_DIRECTORY=True`, `PATH_USES_DOTS=False` |
| JavaScript | `.js`  | `class_declaration` | — |
| TypeScript | `.ts`  | `class_declaration` (not `interface_declaration` — see gaps) | — |

## `CodeParser` (`source_parser.py`)
- `load_languages()` builds one `LanguageConfig` per registered language:
  compiles the grammar (`module.get_language()`), a `Parser`, and both
  `Query` objects (`QUERY`, `REF_QUERY`), wrapping any failure in
  `LanguageLoadError`. Configs are keyed by file extension.
- `CodeParser.parse_file(file_path, content)`:
  1. `validate_file(file_path)` — raises `UnsupportedFileExtensionError` if
     the suffix isn't registered.
  2. Parses the raw bytes with the matching tree-sitter `Parser`, wrapping
     any parser exception in `TreeSitterParseError`.
  3. Returns a `ParsedFile(tree, query, ref_query, language, content)` — the
     single object every downstream stage operates on.

## Output
One `ParsedFile` per source file, carrying the parse tree, the two compiled
queries for its language, the language name, and the raw content bytes.
