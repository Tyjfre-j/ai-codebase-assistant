# Supported Languages

The ingestion pipeline currently supports four languages via standard Tree-sitter grammars. Each language module lives in `app/ingestion/languages/` and implements the core `LANG_HELPERS` interface.

## Python (`.py`)
- **Queries**: Extracts functions, classes, and comprehensive import forms (absolute, relative, aliases, wildcards).
- **Features**: Fully supports class method inheritance resolution and unwrapping of decorated functions. Contains an extensive list of `BUILTINS`.

## JavaScript (`.js`) & TypeScript (`.ts`)
- **Queries**: Extracts functions, classes, arrow functions attached to variables, and class fields. For TS, also extracts interfaces.
- **Features**: Properly handles ES Module imports, namespace imports, and arrow-function class member unwrapping. 

## Go (`.go`)
- **Queries**: Extracts functions, methods with receivers, and structs/interfaces. 
- **Features**: Go's package imports are handled uniquely (directories rather than files). Method receivers are parsed to properly link methods to their defining struct.
