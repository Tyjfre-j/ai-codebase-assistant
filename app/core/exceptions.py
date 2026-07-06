



class RepositoryError(Exception):
    """Base exception for repository operations."""


class InvalidRepositoryURLError(RepositoryError):
    """Raised when a repo URL uses a disallowed scheme, host, or resolves to a private IP."""


class InvalidRefError(RepositoryError):
    """Raised when a ref string fails validation or starts with a dash."""


class RepositoryTooLargeError(RepositoryError):
    """Raised when the cloned repo exceeds MAX_REPO_SIZE_MB."""


class CloneTimeoutError(RepositoryError):
    """Raised when git clone exceeds the configured timeout."""


class EmptyRepositoryError(RepositoryError):
    """Raised when the repository has no commits."""