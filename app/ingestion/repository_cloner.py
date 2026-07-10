from __future__ import annotations

import ipaddress
import re
import shutil
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.core.constants import (
    ALLOWED_REPOSITORY_HOSTS,
    CLONE_TIMEOUT_SECONDS,
    MAX_REF_LENGTH,
    MAX_REPO_SIZE_MB,
)
from app.core.exceptions import (
    CloneTimeoutError,
    EmptyRepositoryError,
    InvalidRefError,
    InvalidRepositoryURLError,
    RepositoryTooLargeError,
)


@dataclass(frozen=True)
class ClonedRepo:
    """Metadata for a cloned repository checked out into a temporary path."""
    local_path: Path
    commit_sha: str
    repo_url: str
    size_bytes: int


_REF_RE = re.compile(rf'^[a-zA-Z0-9][a-zA-Z0-9._/\-]{{0,{MAX_REF_LENGTH}}}$')


def _extract_host_from_url(repo_url: str) -> str:
    """Extract the repository host from an allowed URL shape."""
    parsed_url = urlparse(repo_url)

    if parsed_url.scheme == "https":
        return parsed_url.hostname or ""

    if repo_url.startswith("git@"):
        try:
            return repo_url.split("@", 1)[1].split(":", 1)[0]
        except IndexError:
            raise InvalidRepositoryURLError(f"Malformed git@ URL: {repo_url!r}")

    raise InvalidRepositoryURLError(
        f"Scheme not allowed. Only https and git@ are allowed. Got: {repo_url!r}"
    )


def _validate_repo_url(repo_url: str, allowed_hosts: list[str]) -> None:
    """Reject unsupported hosts and hosts resolving to blocked IP ranges."""
    host = _extract_host_from_url(repo_url)

    if host not in allowed_hosts:
        raise InvalidRepositoryURLError(
            f"Host '{host}' is not in the list of allowed hosts: {allowed_hosts}"
        )

    try:
        ip_str = socket.gethostbyname(host)
    except socket.gaierror as exc:
        raise InvalidRepositoryURLError(
            f"Failed to resolve host '{host}': {exc}"
        ) from exc

    ip = ipaddress.ip_address(ip_str)
    if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
        raise InvalidRepositoryURLError(
            f"Host '{host}' resolves to a blocked IP address: {ip_str}"
        )


def _validate_ref(ref: str) -> None:
    """Reject git refs that could be interpreted as flags or unsafe names."""
    if ref.startswith("-"):
        raise InvalidRefError(
            f"Ref must not start with '-' (argument injection risk): {ref!r}"
        )
    if not _REF_RE.match(ref):
        raise InvalidRefError(
            f"Ref contains disallowed characters: {ref!r}"
        )


class RepositoryCloner:
    """Clone a repository into a temporary directory and clean it up on exit."""

    def __init__(
        self,
        max_repo_size_mb: int = MAX_REPO_SIZE_MB,
        clone_timeout_seconds: int = CLONE_TIMEOUT_SECONDS,
        allowed_hosts: list[str] | None = None,
    ) -> None:
        self._max_repo_size_mb = max_repo_size_mb
        self._clone_timeout_seconds = clone_timeout_seconds
        self._allowed_hosts = allowed_hosts or ALLOWED_REPOSITORY_HOSTS
        self._tmpdir: Path | None = None

    def __enter__(self) -> "RepositoryCloner":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._tmpdir and self._tmpdir.exists():
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        return None

    def clone(self, repo_url: str, ref: str | None = None) -> ClonedRepo:
        """Clone a validated repository URL and return checkout metadata."""
        _validate_repo_url(repo_url, self._allowed_hosts)
        if ref is not None:
            _validate_ref(ref)

        self._tmpdir = Path(tempfile.mkdtemp(prefix="repo_clone_"))

        try:
            return self._do_clone(repo_url, ref)
        except Exception:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            raise


    def _do_clone(self, repo_url: str, ref: str | None) -> ClonedRepo:
        clone_command = [
            "git",
            "clone",
            "--depth=1",
            "--no-tags",
            "--config",
            "core.hooksPath=/dev/null",
        ]
        if ref:
            clone_command += ["--branch", ref]
        clone_command += [repo_url, str(self._tmpdir)]

        try:
            subprocess.run(
                clone_command,
                check=True,
                capture_output=True,
                timeout=self._clone_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise CloneTimeoutError(
                f"Clone timed out after {self._clone_timeout_seconds}s: {repo_url}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="replace")
            if (
                "empty repository" in stderr.lower()
                or "did not send all necessary objects" in stderr
            ):
                raise EmptyRepositoryError(
                    f"Repository appears to be empty: {repo_url}"
                ) from exc
            raise InvalidRepositoryURLError(
                f"git clone failed: {stderr[:300]}"
            ) from exc

        files = [path for path in self._tmpdir.rglob("*") if path.is_file()]
        size_bytes = sum(path.stat().st_size for path in files)
        if size_bytes > self._max_repo_size_mb * 1024 * 1024:
            raise RepositoryTooLargeError(
                f"Repo size {size_bytes / 1e6:.1f} MB exceeds limit {self._max_repo_size_mb} MB"
            )

        try:
            result = subprocess.run(
                ["git", "-C", str(self._tmpdir), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            commit_sha = result.stdout.strip()
        except subprocess.CalledProcessError as exc:
            raise EmptyRepositoryError(
                f"Cannot resolve HEAD — repository may be empty: {repo_url}"
            ) from exc

        return ClonedRepo(
            local_path=self._tmpdir,
            commit_sha=commit_sha,
            repo_url=repo_url,
            size_bytes=size_bytes,
        )

