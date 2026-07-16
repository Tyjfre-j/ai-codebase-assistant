"""Resolves import module text (e.g. ".db", "myapp.services") into real file paths on disk."""

from pathlib import Path


def _read_declared_module_path(project_root: str) -> str | None:
    """Read the module path declared by a go.mod at project_root, if present.

    Go import paths always begin with the declaring module's own path (e.g.
    "myrepo/pkg/utils", where "myrepo" comes from `module myrepo` in go.mod) —
    that prefix is not an actual directory on disk and must be stripped before
    joining with project_root, since project_root is wherever the repo happens
    to live, not necessarily a directory named after the module.
    """
    go_mod = Path(project_root) / "go.mod"
    try:
        text = go_mod.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("module "):
            return line[len("module "):].strip()
    return None


def resolve_relative_import(
    module_text: str,
    file_path: str,
    file_extension: str,
    index_filename: str | None,
    *,
    resolves_to_directory: bool = False,
    path_uses_dots: bool = True,
) -> str | None:
    """Resolve a relative import like '.db' or '..services' against the file that contains it."""
    dots = len(module_text) - len(module_text.lstrip("."))
    remainder = module_text[dots:]
    # JS/TS-style relative paths ('./helper', '../lib/thing') leave a leading
    # '/' here once the dots are stripped off. `Path(base) / "/helper"` would
    # silently discard `base` and return just "/helper" (pathlib treats a
    # leading-slash segment as absolute), so it must come off first.
    remainder = remainder.lstrip("/")

    base = Path(file_path).parent
    for _ in range(dots - 1):
        base = base.parent

    if remainder:
        if path_uses_dots:
            base = base / remainder.replace(".", "/")
        else:
            base = base / remainder

    if resolves_to_directory:
        return str(base) if base.is_dir() else None

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
    resolves_to_directory: bool = False,
    path_uses_dots: bool = True,
) -> str | None:
    """Resolve an absolute import like 'myapp.services' against the project root."""
    if resolves_to_directory:
        # Package-path style imports (Go): the import path is prefixed by this
        # repo's own declared module path, which isn't a real directory on
        # disk — strip it (via go.mod) before joining with project_root.
        # Without go.mod (or if the import doesn't match this repo's module),
        # there's nothing safe to guess, so this reports "can't resolve"
        # rather than trying a heuristic that could false-positive.
        declared_module = _read_declared_module_path(project_root)
        if declared_module is None:
            return None
        if module_text == declared_module:
            remainder = ""
        elif module_text.startswith(declared_module + "/"):
            remainder = module_text[len(declared_module) + 1:]
        else:
            # Doesn't match this repo's own module — an external/third-party
            # package path, not something with a local file to point to.
            return None
        base = Path(project_root) / remainder if remainder else Path(project_root)
        return str(base) if base.is_dir() else None

    if path_uses_dots:
        base = Path(project_root) / module_text.replace(".", "/")
    else:
        base = Path(project_root) / module_text

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
    resolves_to_directory: bool = False,
    path_uses_dots: bool = True,
) -> str | None:
    """Dispatch to the relative or absolute resolver based on which capture the module came from."""
    # Strip surrounding quotes (Go's interpreted_string_literal includes them).
    module_text = module_text.strip("\"'`")

    if is_relative:
        return resolve_relative_import(
            module_text, file_path, file_extension, index_filename,
            resolves_to_directory=resolves_to_directory,
            path_uses_dots=path_uses_dots,
        )
    return resolve_absolute_import(
        module_text, project_root, file_extension, index_filename,
        resolves_to_directory=resolves_to_directory,
        path_uses_dots=path_uses_dots,
    )