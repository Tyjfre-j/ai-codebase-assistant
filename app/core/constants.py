import os

MAX_REPO_SIZE_MB = int(os.getenv("MAX_REPO_SIZE_MB", 500))
CLONE_TIMEOUT_SECONDS = int(os.getenv("CLONE_TIMEOUT", 300))
ALLOWED_REPOSITORY_HOSTS: list[str] = os.getenv(
    "ALLOWED_REPOSITORY_HOSTS",
    "github.com,gitlab.com",
).split(",")
MAX_REF_LENGTH: int = 254
MAX_FILE_SIZE_MB_FOR_PARSING: int = 1
CHUNK_ID_HEX_LENGTH = 16
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
BYTES_PER_MB = 1024 * 1024

# Shallow, tag-less clone; hooks disabled so a cloned repo can't execute
# arbitrary code via hook scripts (e.g. post-checkout).
GIT_CLONE_FLAGS = ["--depth=1", "--no-tags", "--config", "core.hooksPath=/dev/null"]

CLONE_ERROR_MESSAGE_MAX_CHARS = 300

DEFAULT_MAX_FILE_SIZE_MB = 5
DEFAULT_CHUNK_BUDGET_CHARS = 1500