
import os
from pathlib import Path

_SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    "target",
    ".idea",
    ".vscode",
}


def iter_source_files(root: str, extensions: set[str]):
    """Yield source files while skipping common dependency/build directories."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in _SKIP_DIRS and not dirname.startswith(".")
        ]
        for filename in filenames:
            if Path(filename).suffix in extensions:
                yield os.path.join(dirpath, filename)
