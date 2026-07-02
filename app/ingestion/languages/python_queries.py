PYTHON_QUERY = """
(function_definition
  name: (identifier) @func.name
  parameters: (parameters) @func.params
) @func.def

(class_definition
  name: (identifier) @class.name
) @class.def

(import_statement
  name: (dotted_name) @import.name
) @import.stmt

(import_statement
  name: (aliased_import
    name: (dotted_name) @import.alias.module
    alias: (identifier) @import.alias.name
  )
) @import.alias.stmt

(import_from_statement
  module_name: (dotted_name) @import.from.module
  name: (dotted_name) @import.from.name
) @import.from.stmt
"""