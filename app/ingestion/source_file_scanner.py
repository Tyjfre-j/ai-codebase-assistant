
import os
from pathlib import Path

from app.core.constants import _SKIP_DIRS


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
