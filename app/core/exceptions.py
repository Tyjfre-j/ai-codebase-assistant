

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


class IngestionError(Exception):
    """Base exception for all ingestion pipeline operations."""

class UnsupportedFileExtensionError(IngestionError):
    """Raised when a file's extension has no matching language config."""

class FileAccessError(IngestionError):
    """Raised when a file's metadata or content can't be read from disk."""

class LanguageLoadError(IngestionError):
    """Raised when a tree-sitter grammar or query fails to load at startup."""

class TreeSitterParseError(IngestionError):
    """Raised when tree-sitter fails to parse a file's content."""

class ChunkExtractionError(IngestionError):
    """Raised when converting parsed captures into CodeChunks fails."""