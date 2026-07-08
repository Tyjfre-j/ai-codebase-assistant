
import os
from pathlib import Path

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".pytest_cache", ".mypy_cache", "target",
    ".idea", ".vscode",
}


def iter_source_files(root: str, extensions: set[str]):
    """Yield file paths under root whose extension is in `extensions`,
    skipping common non-source directories (VCS, deps, build output, caches).
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for filename in filenames:
            if Path(filename).suffix in extensions:
                yield os.path.join(dirpath, filename)