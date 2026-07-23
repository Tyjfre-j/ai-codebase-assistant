from tree_sitter import Node

from app.ingestion.code_chunk import ImportBinding, ImportKind
from app.ingestion.languages import LANG_HELPERS
from app.ingestion.refs.import_resolution import resolve_import_path
from app.ingestion.source_text import node_text


def _is_within(candidate: Node, statement: Node) -> bool:
    return statement.start_byte <= candidate.start_byte and statement.end_byte >= candidate.end_byte


def _filter_within(nodes: list[Node], statement: Node) -> list[Node]:
    return [node for node in nodes if _is_within(node, statement)]


def _looks_relative(module_text: str) -> bool:
    return module_text.strip("\"'`").startswith(".")


def _join_module_and_name(module_text: str, name: str) -> str:
    separator = "" if module_text.endswith(".") else "."
    return f"{module_text}{separator}{name}"


def _module_node_and_relativity(
    statement: Node, captures: dict[str, list[Node]], content: bytes
) -> tuple[Node | None, bool]:
    relmodule_nodes = _filter_within(captures.get("import.relmodule", []), statement)
    if relmodule_nodes:
        return relmodule_nodes[0], True
    module_nodes = _filter_within(captures.get("import.module", []), statement)
    if module_nodes:
        module_node = module_nodes[0]
        return module_node, _looks_relative(node_text(module_node, content))
    return None, False


def _bindings_for_statement(
    statement: Node, captures: dict[str, list[Node]], content: bytes
) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for bound_name_node in _filter_within(captures.get("import.bound_name", []), statement):
        bound_name = node_text(bound_name_node, content)
        alias_nodes = _filter_within(captures.get("import.alias", []), statement)
        alias_node = next((n for n in alias_nodes if n.parent == bound_name_node.parent), None)
        alias = node_text(alias_node, content) if alias_node is not None else bound_name
        bindings[bound_name] = alias
    return bindings


def _direct_module_for_bound_name(bound_name_node: Node, direct_module_nodes: list[Node]) -> Node | None:
    for module_node in direct_module_nodes:
        if bound_name_node.parent == module_node:
            return module_node
        if module_node.parent is not None and module_node.parent == bound_name_node.parent:
            return module_node
    return None


def _derived_bindings_for_statement(
    statement: Node,
    captures: dict[str, list[Node]],
    content: bytes,
    derive_bound_name,
) -> list[tuple[str, str, str]]:
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
    parsed,
    file_path: str,
    project_root: str,
    captures: dict[str, list[Node]],
) -> tuple[dict[str, ImportBinding], list[str]]:
    language_helpers = LANG_HELPERS[parsed.language]
    file_extension = language_helpers.FILE_EXTENSION
    index_filename = language_helpers.get_package_index_filename()
    resolves_to_directory = getattr(language_helpers, "RESOLVES_IMPORT_TO_DIRECTORY", False)
    derive_bound_name = getattr(language_helpers, "derive_import_bound_name", None)
    allows_submodule_imports = getattr(language_helpers, "ALLOWS_SUBMODULE_IMPORTS", False)
    plain_import_binding = getattr(language_helpers, "PLAIN_IMPORT_BINDING", "first_component")
    is_relative_module_text = getattr(language_helpers, "is_relative_module_text", None)

    def resolve(module_text: str, is_relative: bool) -> str | None:
        return resolve_import_path(
            module_text, is_relative, file_path, project_root,
            file_extension, index_filename,
            language_helpers=language_helpers,
            resolves_to_directory=resolves_to_directory,
        )

    bindings: dict[str, ImportBinding] = {}
    wildcard_modules: list[str] = []

    for statement in captures.get("import.stmt", []):
        if _filter_within(captures.get("import.wildcard", []), statement):
            module_node, is_relative = _module_node_and_relativity(statement, captures, parsed.content)
            if module_node is None:
                continue
            resolved = resolve(node_text(module_node, parsed.content), is_relative)
            if resolved is not None:
                wildcard_modules.append(resolved)
            continue

        direct_module_nodes = _filter_within(captures.get("import.direct_module", []), statement)
        if direct_module_nodes:
            for bound_name_node in _filter_within(captures.get("import.bound_name", []), statement):
                module_node = _direct_module_for_bound_name(bound_name_node, direct_module_nodes)
                if module_node is None:
                    continue
                module_text = node_text(module_node, parsed.content)
                alias = node_text(bound_name_node, parsed.content)
                resolved = resolve(module_text, _looks_relative(module_text))

                is_unaliased = bound_name_node.parent == module_node
                extra_segments = (
                    module_text.count(".")
                    if is_unaliased and plain_import_binding == "first_component"
                    else 0
                )
                bindings[alias] = ImportBinding(
                    local_name=alias,
                    resolved_path=resolved,
                    remote_name=alias,
                    kind=ImportKind.MODULE,
                    extra_segments=extra_segments,
                )
            continue

        statement_bindings = _bindings_for_statement(statement, captures, parsed.content)
        if statement_bindings:
            module_node, is_relative = _module_node_and_relativity(statement, captures, parsed.content)
            shared_module_text = node_text(module_node, parsed.content) if module_node is not None else None

            for bound_name, alias in statement_bindings.items():
                if shared_module_text is not None and allows_submodule_imports:
                    submodule_text = _join_module_and_name(shared_module_text, bound_name)
                    submodule_path = resolve(submodule_text, is_relative)
                    if submodule_path is not None:
                        resolved, kind = submodule_path, ImportKind.MODULE
                    else:
                        resolved, kind = resolve(shared_module_text, is_relative), ImportKind.NAMED
                elif shared_module_text is not None:
                    resolved, kind = resolve(shared_module_text, is_relative), ImportKind.NAMED
                else:
                    resolved, kind = resolve(bound_name, False), ImportKind.MODULE

                bindings[alias] = ImportBinding(
                    local_name=alias,
                    resolved_path=resolved,
                    remote_name=bound_name,
                    kind=kind,
                    extra_segments=0,
                )
            continue

        if derive_bound_name is not None:
            for module_text, bound_name, alias in _derived_bindings_for_statement(
                statement, captures, parsed.content, derive_bound_name
            ):
                is_relative = is_relative_module_text(module_text) if is_relative_module_text else False
                resolved = resolve(module_text, is_relative)
                bindings[alias] = ImportBinding(
                    local_name=alias,
                    resolved_path=resolved,
                    remote_name=bound_name,
                    kind=ImportKind.MODULE,
                    extra_segments=0,
                )

    return bindings, wildcard_modules