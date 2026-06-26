
import pytest
import socket
from unittest.mock import patch
from app.core.constants import ALLOWED_REPOSITORY_HOSTS
from app.core.exceptions import InvalidRepositoryURLError
from app.ingestion.cloner import _extract_host_from_url, _validate_repo_url


def test_scheme_rejection():
    # invalide scheme
    with pytest.raises(InvalidRepositoryURLError, match="Scheme not allowed") as error:
        _extract_host_from_url("ftp://github.com/user/repo.git")

def test_scheme_acceptance():
    # valid scheme
    _extract_host_from_url("https://github.com/owner/repo")
    _extract_host_from_url("git@github.com:owner/repo.git")

def test_host_rejection():
    # invalid host
    with pytest.raises(InvalidRepositoryURLError, match="Host 'bitbucket.org' is not in the list of allowed hosts") as error:
        _validate_repo_url("https://bitbucket.org/owner/repo.git", allowed_hosts = ALLOWED_REPOSITORY_HOSTS)

def test_extracts_github_host():
    result = _extract_host_from_url("https://github.com/owner/repo")
    assert result == "github.com"

def test_extracts_gitlab_host():
    result = _extract_host_from_url("https://gitlab.com/owner/repo")
    assert result == "gitlab.com"

def test_extracts_host_from_git_at():
    result = _extract_host_from_url("git@github.com:owner/repo.git")
    assert result == "github.com"

def test_passes_when_ip_is_public():
    with patch("app.ingestion.cloner.socket.gethostbyname", return_value="140.82.114.4"):
        _validate_repo_url("https://github.com/owner/repo", ALLOWED_REPOSITORY_HOSTS)

def test_rejects_when_ip_is_private():
    with patch("app.ingestion.cloner.socket.gethostbyname", return_value="192.168.1.1"):
        with pytest.raises(InvalidRepositoryURLError, match="192.168.1.1"):
            _validate_repo_url("https://github.com/owner/repo", ALLOWED_REPOSITORY_HOSTS)

def test_rejects_when_ip_is_loopback():
    with patch("app.ingestion.cloner.socket.gethostbyname", return_value="127.0.0.1"):
        with pytest.raises(InvalidRepositoryURLError, match="127.0.0.1"):
            _validate_repo_url("https://github.com/owner/repo", ALLOWED_REPOSITORY_HOSTS)

def test_rejects_when_ip_is_link_local():
    with patch("app.ingestion.cloner.socket.gethostbyname", return_value="169.254.1.1"):
        with pytest.raises(InvalidRepositoryURLError, match="169.254.1.1"):
            _validate_repo_url("https://github.com/owner/repo", ALLOWED_REPOSITORY_HOSTS)

def test_rejects_when_ip_is_reserved():
    with patch("app.ingestion.cloner.socket.gethostbyname", return_value="240.0.0.1"):
        with pytest.raises(InvalidRepositoryURLError, match="240.0.0.1"):
            _validate_repo_url("https://github.com/owner/repo", ALLOWED_REPOSITORY_HOSTS)

def test_rejects_when_host_cannot_be_resolved():
    with patch("app.ingestion.cloner.socket.gethostbyname", side_effect=socket.gaierror("Name or service not known")):
        with pytest.raises(InvalidRepositoryURLError, match="Failed to resolve host"):
            _validate_repo_url("https://github.com/owner/repo", ALLOWED_REPOSITORY_HOSTS)