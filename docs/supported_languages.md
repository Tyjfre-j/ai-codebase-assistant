# Supported Languages

The ingestion pipeline currently supports four languages via standard Tree-sitter grammars. Each language module lives in `app/ingestion/languages/` and implements the core `LANG_HELPERS` interface (`REQUIRED_ATTRS`), providing custom queries and AST unwrapping tools.

## Python (`.py`)
- **Queries**: Extracts functions, classes, and comprehensive import forms (absolute, relative, aliases, wildcards). `REF_QUERY` captures calls, attribute access, and base class inheritance.
- **Features**: 
  - Fully supports class method inheritance resolution (`get_enclosing_class_name`).
  - Correctly unwraps decorated functions (`@decorator def foo()`) via `unwrap_decorated_definition_node` to ensure decorators aren't lost and the inner function is parsed correctly.
  - Generates comprehensive class skeleton stubs including `async def` and decorators.
  - Exposes an extensive list of native `BUILTINS` (e.g. `print`, `set`, `os.path.exists`) via `is_builtin`.

## JavaScript (`.js`) & TypeScript (`.ts`)
- **Queries**: Extracts functions, classes, arrow functions attached to variables, and class fields. For TS, also extracts interfaces. `REF_QUERY` captures calls, object property calls, and base class inheritance (`class_heritage` / `extends_clause`).
- **Features**: 
  - Properly handles ES Module imports, namespace imports, and default imports.
  - Specialized `_unwrap_arrow_field` helper unwraps arrow-function class members from their parent property fields.
  - Generates compact class skeletons for both standard `method_definition`s and arrow-function fields.
  - Standard JS `BUILTINS` implemented (e.g., `console`, `Math`, `Promise`).

## Go (`.go`)
- **Queries**: Extracts functions, methods with receivers, and structs/interfaces. `REF_QUERY` captures direct calls, selector expressions (`obj.Method()`), and struct embedding.
- **Features**: 
  - Go's package imports are handled uniquely: imports resolve to directories rather than specific `.go` files (`RESOLVES_IMPORT_TO_DIRECTORY = True`).
  - `get_enclosing_class_name` parses method receivers (`func (r *Receiver)`) to correctly link Go methods to their defining struct, even though they sit top-level in the AST.
  - `derive_import_bound_name` implicitly derives the bound name of Go imports (e.g., `import "encoding/json"` -> `json`).
  - Standard Go `BUILTINS` implemented (e.g., `make`, `append`, `len`).
