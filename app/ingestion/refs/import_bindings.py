from tree_sitter import Node

from app.ingestion.code_chunk import ImportKind
from app.ingestion.languages import LANG_HELPERS
from app.ingestion.refs.import_resolution import resolve_import_path
from app.ingestion.source_parser import ParsedFile
from app.ingestion.source_text import node_text


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


def _derived_bindings_for_statement(
    statement: Node,
    captures: dict[str, list[Node]],
    content: bytes,
    derive_bound_name,
) -> list[tuple[str, str, str]]:
    """Return (module_text, bound_name, alias) for each module path in a statement.

    Used for grammars (Go) where the identifier bound at call sites is never
    an explicit AST node for the unaliased case, so `_bindings_for_statement`
    finds nothing. One `import.stmt` capture can still cover a *grouped*
    statement with several `import.module` nodes inside it (Go's
    `import (...)` block), so every module node is handled individually here
    rather than only the first, unlike the shared-module-text path below.
    """
    module_nodes = _filter_within(captures.get("import.module", []), statement)
    alias_nodes = _filter_within(captures.get("import.alias", []), statement)

    results: list[tuple[str, str, str]] = []
    for module_node in module_nodes:
        module_text = node_text(module_node, content)
        bound_name = derive_bound_name(module_text)
        alias_node = next((n for n in alias_nodes if n.parent == module_node.parent), None)
        alias = node_text(alias_node, content) if alias_node is not None else bound_name
        results.append((module_text, bound_name, alias))
    return results


def extract_import_bindings_for_file(
    parsed: ParsedFile,
    file_path: str,
    project_root: str,
    captures: dict[str, list[Node]],
) -> dict[str, tuple[str | None, str, str]]:
    """Return alias_or_bound_name -> (resolved_path_or_None, bound_name, import_kind) for every import in a file.

    `captures` is the same dict `chunk_file` already built by running the
    definitions/imports query once for this file — passed in here instead of
    re-running that query a second time against the same parsed tree.
    """
    language_helpers = LANG_HELPERS[parsed.language]
    file_extension = language_helpers.FILE_EXTENSION
    index_filename = language_helpers.get_module_index_filename()
    resolves_to_directory = getattr(language_helpers, "RESOLVES_IMPORT_TO_DIRECTORY", False)
    path_uses_dots = getattr(language_helpers, "PATH_USES_DOTS", True)
    derive_bound_name = getattr(language_helpers, "derive_import_bound_name", None)
    bindings: dict[str, tuple[str | None, str, str]] = {}

    for statement in captures.get("import.stmt", []):
        statement_bindings = _bindings_for_statement(statement, captures, parsed.content)

        if statement_bindings:
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
                    # "from X import Y" shape: a module was named separately from what's bound,
                    # so `bound_name` is a specific symbol pulled out of that module.
                    resolved = resolve_import_path(
                        shared_module_text, is_relative, file_path, project_root,
                        file_extension, index_filename,
                    )
                    import_kind = ImportKind.NAMED
                else:
                    # "import X" shape: there's no separate module capture, so the bound
                    # name itself IS the module.
                    resolved = resolve_import_path(
                        bound_name, False, file_path, project_root,
                        file_extension, index_filename,
                    )
                    import_kind = ImportKind.MODULE

                bindings[alias] = (resolved, bound_name, import_kind)

        elif derive_bound_name is not None:
            # No explicit bound-name node in this statement at all (Go's plain
            # `import "path"`) — derive one binding per module path in it. Each
            # binding here always names the whole imported package/module.
            for module_text, bound_name, alias in _derived_bindings_for_statement(
                statement, captures, parsed.content, derive_bound_name
            ):
                resolved = resolve_import_path(
                    module_text, False, file_path, project_root,
                    file_extension, index_filename,
                    resolves_to_directory=resolves_to_directory,
                    path_uses_dots=path_uses_dots,
                )
                bindings[alias] = (resolved, bound_name, ImportKind.MODULE)

    return bindings