import os

MAX_REPO_SIZE_MB = int(os.getenv("MAX_REPO_SIZE_MB", 500))
CLONE_TIMEOUT_SECONDS = int(os.getenv("CLONE_TIMEOUT", 300))
ALLOWED_REPOSITORY_HOSTS: list[str] = os.getenv(
    "ALLOWED_REPOSITORY_HOSTS",
    "github.com,gitlab.com",
).split(",")
MAX_REF_LENGTH: int = 254
MAX_FILE_SIZE_MB_FOR_PARSING = int = 1