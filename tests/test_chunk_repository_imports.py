# tests/test_chunk_repository_imports.py
from app.ingestion.repo_chunker import chunk_repository  

def test_chunk_repository_populates_import_bindings(project):
    results = chunk_repository(project["root"])
    users_file = next(r for r in results if r.file_path.endswith("users.py"))
    assert users_file.import_bindings != {}
    assert "get_user" in users_file.import_bindings
    assert "gu" in users_file.import_bindings