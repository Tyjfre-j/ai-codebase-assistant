JS_QUERY = """
(function_declaration
  name: (identifier) @func.name
  parameters: (formal_parameters) @func.params
) @func.def

(method_definition
  name: (property_identifier) @func.name
  parameters: (formal_parameters) @func.params
) @func.def

(variable_declarator
  name: (identifier) @func.name
  value: (arrow_function
    parameters: (formal_parameters) @func.params
  )
) @func.def

(class_declaration
  name: (identifier) @class.name
) @class.def

(import_statement
  (import_clause
    (named_imports
      (import_specifier
        name: (identifier) @import.name
        alias: (identifier)? @import.alias
      )
    )
  )
  source: (string) @import.source
) @import.stmt

(import_statement
  (import_clause
    (identifier) @import.default
  )
  source: (string) @import.source
) @import.stmt

(import_statement
  (import_clause
    (namespace_import
      (identifier) @import.namespace
    )
  )
  source: (string) @import.source
) @import.stmt

(import_statement
  "import" . source: (string) @import.source
) @import.stmt
"""