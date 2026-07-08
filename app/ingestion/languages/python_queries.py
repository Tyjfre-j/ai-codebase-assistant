PYTHON_QUERY = """
(function_definition
  name: (identifier) @func.name
  parameters: (parameters) @func.params
) @func.def

(class_definition
  name: (identifier) @class.name
) @class.def

(import_statement
  name: (dotted_name) @import.module
) @import.stmt

(import_statement
  name: (aliased_import
    name: (dotted_name) @import.module
    alias: (identifier) @import.alias
  )
) @import.stmt

(import_from_statement
  module_name: (dotted_name) @import.module
  name: (dotted_name) @import.bound_name
) @import.stmt

(import_from_statement
  module_name: (dotted_name) @import.module
  name: (aliased_import
    name: (dotted_name) @import.bound_name
    alias: (identifier) @import.alias
  )
) @import.stmt

(import_from_statement
  module_name: (relative_import) @import.relmodule
  name: (dotted_name) @import.bound_name
) @import.stmt

(import_from_statement
  module_name: (relative_import) @import.relmodule
  name: (aliased_import
    name: (dotted_name) @import.bound_name
    alias: (identifier) @import.alias
  )
) @import.stmt

(import_from_statement
  module_name: (dotted_name) @import.module
  (wildcard_import) @import.wildcard
) @import.stmt

(import_from_statement
  module_name: (relative_import) @import.relmodule
  (wildcard_import) @import.wildcard
) @import.stmt
"""

CLASS_NODE_TYPES = {"class_definition"}
WRAPPER_TYPES = {"function_definition", "class_definition"}


def resolve_definition_node(def_node):
    """Unwrap to the decorated_definition parent, if present, so decorators aren't lost."""
    if def_node.parent is not None and def_node.parent.type == "decorated_definition":
        return def_node.parent
    return def_node


def get_member_info(node, content: bytes):
    """For class-skeleton building: identify a method node and its stub signature."""
    from app.ingestion.chunk_builder_helpers import node_text

    target = None
    decorators: list[str] = []
    if node.type == "decorated_definition":
        inner = node.child_by_field_name("definition")
        if inner is not None and inner.type == "function_definition":
            target = inner
            decorators = [node_text(d, content) for d in node.children if d.type == "decorator"]
    elif node.type == "function_definition":
        target = node

    if target is None:
        return None

    name = node_text(target.child_by_field_name("name"), content)
    params = node_text(target.child_by_field_name("parameters"), content)
    prefix = "async def" if any(c.type == "async" for c in target.children) else "def"
    return {"name": name, "params": params, "decorators": decorators, "prefix": prefix}