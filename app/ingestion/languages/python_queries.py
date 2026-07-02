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
"""