"""Resolves import module text (e.g. ".db", "myapp.services") into real file paths on disk."""

from pathlib import Path


def resolve_relative_import(module_text: str, file_path: str) -> str | None:
    """Resolve a relative import like '.db' or '..services' against the file that contains it."""
    dots = len(module_text) - len(module_text.lstrip("."))
    remainder = module_text[dots:]

    base = Path(file_path).parent
    for _ in range(dots - 1):
        base = base.parent

    if remainder:
        base = base / remainder.replace(".", "/")

    as_module = base.with_suffix(".py")
    if as_module.exists():
        return str(as_module)

    as_package = base / "__init__.py"
    if as_package.exists():
        return str(as_package)

    return None


def resolve_absolute_import(module_text: str, project_root: str) -> str | None:
    """Resolve an absolute import like 'myapp.services' against the project root."""
    base = Path(project_root) / module_text.replace(".", "/")

    as_module = base.with_suffix(".py")
    if as_module.exists():
        return str(as_module)

    as_package = base / "__init__.py"
    if as_package.exists():
        return str(as_package)

    return None


def resolve_import_path(
    module_text: str, is_relative: bool, file_path: str, project_root: str
) -> str | None:
    """Dispatch to the relative or absolute resolver based on which capture the module came from."""
    if is_relative:
        return resolve_relative_import(module_text, file_path)
    return resolve_absolute_import(module_text, project_root)