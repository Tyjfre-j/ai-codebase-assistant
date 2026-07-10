
import subprocess

import pytest
import socket
from unittest.mock import MagicMock, patch
from app.core.constants import ALLOWED_REPOSITORY_HOSTS
from app.core.exceptions import CloneTimeoutError, EmptyRepositoryError, InvalidRefError, InvalidRepositoryURLError, RepositoryTooLargeError
from app.ingestion.repository_cloner import RepositoryCloner, _extract_host_from_url, _validate_ref, _validate_repo_url


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
    with patch("app.ingestion.repository_cloner.socket.gethostbyname", return_value="140.82.114.4"):
        _validate_repo_url("https://github.com/owner/repo", ALLOWED_REPOSITORY_HOSTS)

def test_rejects_when_ip_is_private():
    with patch("app.ingestion.repository_cloner.socket.gethostbyname", return_value="192.168.1.1"):
        with pytest.raises(InvalidRepositoryURLError, match="192.168.1.1"):
            _validate_repo_url("https://github.com/owner/repo", ALLOWED_REPOSITORY_HOSTS)

def test_rejects_when_ip_is_loopback():
    with patch("app.ingestion.repository_cloner.socket.gethostbyname", return_value="127.0.0.1"):
        with pytest.raises(InvalidRepositoryURLError, match="127.0.0.1"):
            _validate_repo_url("https://github.com/owner/repo", ALLOWED_REPOSITORY_HOSTS)

def test_rejects_when_ip_is_link_local():
    with patch("app.ingestion.repository_cloner.socket.gethostbyname", return_value="169.254.1.1"):
        with pytest.raises(InvalidRepositoryURLError, match="169.254.1.1"):
            _validate_repo_url("https://github.com/owner/repo", ALLOWED_REPOSITORY_HOSTS)

def test_rejects_when_ip_is_reserved():
    with patch("app.ingestion.repository_cloner.socket.gethostbyname", return_value="240.0.0.1"):
        with pytest.raises(InvalidRepositoryURLError, match="240.0.0.1"):
            _validate_repo_url("https://github.com/owner/repo", ALLOWED_REPOSITORY_HOSTS)

def test_rejects_when_host_cannot_be_resolved():
    with patch("app.ingestion.repository_cloner.socket.gethostbyname", side_effect=socket.gaierror("Name or service not known")):
        with pytest.raises(InvalidRepositoryURLError, match="Failed to resolve host"):
            _validate_repo_url("https://github.com/owner/repo", ALLOWED_REPOSITORY_HOSTS)

def test_ref_rejects_leading_dash():
    with pytest.raises(InvalidRefError, match="Ref must not start with '-'"):
        _validate_ref("-malicious-ref")


def test_ref_rejects_disallowed_characters():
    with pytest.raises(InvalidRefError, match="Ref contains disallowed characters"):
        _validate_ref("feat;rm -rf /")

def test_ref_accepts_valid_ref():
    # This should not raise an exception
    _validate_ref("feature/new-feature")

def test_repository_cloner_workflow(tmp_path):
    with patch("app.ingestion.repository_cloner.socket.gethostbyname", return_value="140.82.114.4"):
        with patch("app.ingestion.repository_cloner.tempfile.mkdtemp", return_value=str(tmp_path)):
            with patch("app.ingestion.repository_cloner.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0),                          # first call — git clone
                    MagicMock(returncode=0, stdout="a" * 40 + "\n"),  # second call — rev-parse
                ]
                with RepositoryCloner() as cloner:
                    result = cloner.clone("https://github.com/owner/repo")

                assert result.commit_sha == "a" * 40
                assert result.repo_url == "https://github.com/owner/repo"
                assert result.local_path == tmp_path
                assert result.size_bytes == 0  # Since we didn't actually clone anything, size is 0
                assert mock_run.call_count == 2

def test_repository_cloner_clone_timeout(tmp_path):
    with patch("app.ingestion.repository_cloner.socket.gethostbyname", return_value="140.82.114.4"):
        with patch("app.ingestion.repository_cloner.tempfile.mkdtemp", return_value=str(tmp_path)):
            with patch("app.ingestion.repository_cloner.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=5)
                with RepositoryCloner() as cloner:
                    with pytest.raises(CloneTimeoutError):
                        cloner.clone("https://github.com/owner/repo")
                    
                    assert not tmp_path.exists()

def test_repository_cloner_size_limit_exceeded(tmp_path):
    with patch("app.ingestion.repository_cloner.socket.gethostbyname", return_value="140.82.114.4"):
                with patch("app.ingestion.repository_cloner.tempfile.mkdtemp", return_value=str(tmp_path)):
                    with patch("app.ingestion.repository_cloner.subprocess.run") as mock_run:
                        mock_run.side_effect = [
                            MagicMock(returncode=0),                          # first call — git clone
                        ]
                        (tmp_path / "somefile.txt").write_bytes(b"x")
                        with RepositoryCloner(max_repo_size_mb=0) as cloner:
                            with pytest.raises(RepositoryTooLargeError, match="exceeds limit"):
                                cloner.clone("https://github.com/owner/repo")

def test_repository_cloner_empty_repo(tmp_path):
     with patch("app.ingestion.repository_cloner.socket.gethostbyname", return_value="140.82.114.4"):
                with patch("app.ingestion.repository_cloner.tempfile.mkdtemp", return_value=str(tmp_path)):
                    with patch("app.ingestion.repository_cloner.subprocess.run") as mock_run:
                        mock_run.side_effect = [
                            MagicMock(returncode=0),                          # first call — git clone
                            subprocess.CalledProcessError(returncode=128, cmd="git rev-parse HEAD", stderr=b"fatal: your repository is empty\n"),  # second call — rev-parse
                        ]
                        with RepositoryCloner() as cloner:
                            with pytest.raises(EmptyRepositoryError, match="repository may be empty"):
                                cloner.clone("https://github.com/owner/repo")
    
def test_repository_cloner_clone_cleans_up_on_error(tmp_path):
     with patch("app.ingestion.repository_cloner.socket.gethostbyname", return_value="140.82.114.4"):
                with patch("app.ingestion.repository_cloner.tempfile.mkdtemp", return_value=str(tmp_path)):
                    with patch("app.ingestion.repository_cloner.subprocess.run") as mock_run:
                        mock_run.side_effect = [
                             MagicMock(returncode=0),
                             MagicMock(returncode=0, stdout="a" * 40 + "\n")
                        ]
                        with pytest.raises(Exception, match="Simulated error after cloning"):
                            with RepositoryCloner() as cloner:           
                                result = cloner.clone("https://github.com/owner/repo")
                                raise Exception("Simulated error after cloning")
                        assert not tmp_path.exists()  # Ensure the temporary directory is cleaned up after the context manager exits