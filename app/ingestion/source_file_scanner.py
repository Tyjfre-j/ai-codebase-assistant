
import os
from pathlib import Path

from app.core.constants import _SKIP_DIRS


def iter_source_files(root: str, extensions: set[str]):
    """Yield source files while skipping common dependency/build directories."""
    # Walk the directory tree starting from the root, skipping directories in _SKIP_DIRS and hidden directories.
    # check app/core/constants.py for details on what _SKIP_DIRS contains
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in _SKIP_DIRS and not dirname.startswith(".")
        ]
        # Yield files that have an extension in the provided set of extensions.
        # extensions are passed in from the chunk_repository function in app/ingestion/repo_chunker.py
        # which gets them from the CodeParser object
        for filename in filenames:
            if Path(filename).suffix in extensions:
                yield os.path.join(dirpath, filename)
