




class InvalidRepositoryURLError(ValueError):
    """Raised when a repo URL uses a disallowed scheme, host, or resolves to a private IP."""

class InvalidRefError(ValueError):
    """Raised when a ref string fails validation or starts with a dash."""

class RepositoryTooLargeError(RuntimeError):
    """Raised when the cloned repo exceeds MAX_REPO_SIZE_MB."""

class CloneTimeoutError(RuntimeError):
    """Raised when git clone exceeds the configured timeout."""

class EmptyRepositoryError(RuntimeError):
    """Raised when the repository has no commits."""