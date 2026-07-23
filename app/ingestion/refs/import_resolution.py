
from pathlib import Path


def resolve_relative_import(
    module_text: str,
    file_path: str,
    file_extension: str,
    index_filename: str | None,
    *,
    language_helpers,
    resolves_to_directory: bool = False,
) -> str | None:
    """Resolve a relative import by delegating the syntax-specific parsing
    (how many levels to climb, what path remains) to the language module."""
    parse_fn = getattr(language_helpers, "parse_relative_module", None)
    if parse_fn is None:
        return None

    levels, remainder = parse_fn(module_text)

    base = Path(file_path).parent
    for _ in range(levels):
        base = base.parent

    if remainder:
        base = base / remainder

    if resolves_to_directory:
        return str(base) if base.is_dir() else None

    if remainder:
        as_module = base.with_suffix(file_extension)
        if as_module.exists():
            return str(as_module)

    if index_filename is not None:
        as_package = base / index_filename
        if as_package.exists():
            return str(as_package)

    return None


def resolve_absolute_import(
    module_text: str,
    project_root: str,
    file_extension: str,
    index_filename: str | None,
    *,
    language_helpers,
    resolves_to_directory: bool = False,
) -> str | None:
    if resolves_to_directory:
        resolve_fn = getattr(language_helpers, "resolve_declared_root", None)
        return resolve_fn(module_text, project_root) if resolve_fn else None

    to_path_segment = getattr(language_helpers, "module_text_to_path_segment", None)
    path_segment = to_path_segment(module_text) if to_path_segment else module_text
    base = Path(project_root) / path_segment

    as_module = base.with_suffix(file_extension)
    if as_module.exists():
        return str(as_module)

    if index_filename is not None:
        as_package = base / index_filename
        if as_package.exists():
            return str(as_package)

    return None


def resolve_import_path(
    module_text: str,
    is_relative: bool,
    file_path: str,
    project_root: str,
    file_extension: str,
    index_filename: str | None,
    *,
    language_helpers,
    resolves_to_directory: bool = False,
) -> str | None:
    module_text = module_text.strip("\"'`")

    if is_relative:
        return resolve_relative_import(
            module_text, file_path, file_extension, index_filename,
            language_helpers=language_helpers,
            resolves_to_directory=resolves_to_directory,
        )
    return resolve_absolute_import(
        module_text, project_root, file_extension, index_filename,
        language_helpers=language_helpers,
        resolves_to_directory=resolves_to_directory,
    )