# Step 1 — Repository Cloning

**Module:** `app/ingestion/repository_cloner.py`
**Entry point:** `RepositoryCloner.clone(repo_url, ref=None)`

## Purpose
Safely clone an external git repository into a temporary directory so the rest of the ingestion pipeline has a local checkout to walk.

## What it does
1. **URL validation** (`_validate_repo_url`) — extracts the host from the URL (`https://` or `git@` form only) and rejects anything not in `ALLOWED_REPOSITORY_HOSTS`.
2. **DNS / SSRF guard** — resolves the host via `socket.gethostbyname` and rejects private, loopback, reserved, or link-local IPs. This check runs once up front and again immediately before the actual `git clone` call, to narrow a DNS-rebinding TOCTOU window.
3. **Ref validation** (`_validate_ref`) — rejects refs starting with `-` (argument-injection risk) and enforces a whitelist regex.
4. **Clone** — runs `git clone <flags> [--branch ref] <url> <tmpdir>` with a timeout (`CLONE_TIMEOUT_SECONDS`), raising `CloneTimeoutError` or `InvalidRepositoryURLError` on failure.
5. **Symlink-aware size check** — walks the clone with `rglob("*")`, explicitly excluding symlinks, sums real file sizes, and raises `RepositoryTooLargeError` if it exceeds `MAX_REPO_SIZE_MB`.
6. **HEAD resolution** — runs `git rev-parse HEAD`; if that fails the repo is treated as empty (`EmptyRepositoryError`).
7. **Cleanup** — `__exit__` always removes the temp directory via `shutil.rmtree(..., ignore_errors=True)`.

## Output
`ClonedRepo(local_path, commit_sha, repo_url, size_bytes)` — an immutable record consumed by the next stage (file discovery).

## Security notes
- Only `https://` and `git@` URL shapes are accepted.
- Symlinks are excluded from size calculation to prevent reading arbitrary host files.
