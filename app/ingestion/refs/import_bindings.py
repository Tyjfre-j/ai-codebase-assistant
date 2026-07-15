from tree_sitter import Node

from app.ingestion.chunking.query_captures import run_captures
from app.ingestion.source_parser import ParsedFile
from app.ingestion.source_text import node_text
from app.ingestion.refs.import_resolution import resolve_import_path


def _is_within(candidate: Node, statement: Node) -> bool:
    return statement.start_byte <= candidate.start_byte and statement.end_byte >= candidate.end_byte


def _filter_within(nodes: list[Node], statement: Node) -> list[Node]:
    return [node for node in nodes if _is_within(node, statement)]


def _bindings_for_statement(
    statement: Node, captures: dict[str, list[Node]], content: bytes
) -> dict[str, str]:
    """Return a mapping of bound_name -> alias for a single import statement."""
    bindings: dict[str, str] = {}
    for bound_name_node in _filter_within(captures.get("import.bound_name", []), statement):
        bound_name = node_text(bound_name_node, content)
        alias_nodes = _filter_within(captures.get("import.alias", []), statement)
        alias_node = next((n for n in alias_nodes if n.parent == bound_name_node.parent), None)
        alias = node_text(alias_node, content) if alias_node is not None else bound_name
        bindings[bound_name] = alias
    return bindings


def extract_import_bindings_for_file(
    parsed: ParsedFile, file_path: str, project_root: str
) -> dict[str, tuple[str | None, str]]:
    """Return a mapping of alias_or_bound_name -> (resolved_path_or_None, bound_name) for every import in a file."""
    captures = run_captures(parsed)
    bindings: dict[str, tuple[str | None, str]] = {}

    for statement in captures.get("import.stmt", []):
        statement_bindings = _bindings_for_statement(statement, captures, parsed.content)

        module_nodes = _filter_within(captures.get("import.module", []), statement)
        relmodule_nodes = _filter_within(captures.get("import.relmodule", []), statement)

        if relmodule_nodes:
            module_node, is_relative = relmodule_nodes[0], True
        elif module_nodes:
            module_node, is_relative = module_nodes[0], False
        else:
            module_node, is_relative = None, False

        shared_module_text = (
            node_text(module_node, parsed.content) if module_node is not None else None
        )

        for bound_name, alias in statement_bindings.items():
            if shared_module_text is not None:
                resolved = resolve_import_path(
                    shared_module_text, is_relative, file_path, project_root
                )
            else:
                resolved = resolve_import_path(bound_name, False, file_path, project_root)

            bindings[alias] = (resolved, bound_name)

    return bindings