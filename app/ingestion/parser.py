from dataclasses import dataclass
from pathlib import Path

import tree_sitter_go as tsgo
import tree_sitter_javascript as tsjs
import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser, Query, Tree

from app.core.constants import MAX_FILE_SIZE_MB_FOR_PARSING
from app.ingestion.file_validation import (
    is_file_binary,
    is_file_empty,
    is_file_minified,
    is_file_oversized,
)
from app.ingestion.languages.go_queries import GO_QUERY
from app.ingestion.languages.javascript_queries import JS_QUERY
from app.ingestion.languages.python_queries import PYTHON_QUERY
from app.ingestion.languages.typescript_queries import TS_QUERY


@dataclass
class LanguageConfig:
    name: str
    language: Language
    query: Query


def load_languages() -> dict[str, LanguageConfig]:
    specs = [
        # (extension, name, loader_function, query_string)
        (".py", "python", tspython.language, PYTHON_QUERY),
        (".go", "go", tsgo.language, GO_QUERY),
        (".ts", "typescript", tsts.language_typescript, TS_QUERY),
        (".js", "javascript", tsjs.language, JS_QUERY),
    ]
    
    configs: dict[str, LanguageConfig] = {}

    for ext, name, loader_fn, query_str in specs:
        try:
            lang = Language(loader_fn())
            query = Query(lang, query_str)
        except Exception as e:
            raise RuntimeError(f"Failed to load language for extension {ext}: {e}") from e

        configs[ext] = LanguageConfig(name=name, language=lang, query=query)

    return configs

class CodeParser:
    def __init__(self):
        self.language_configs = load_languages()

    def get_language_config(self, file_extension: str) -> LanguageConfig | None:
        return self.language_configs.get(file_extension)

    def validate_file(self, file_path: str) -> None:
        """Raise ValueError if the file's extension isn't supported."""
        file_extension = Path(file_path).suffix
        if file_extension not in self.language_configs:
            raise ValueError(f"Unsupported file extension: {file_extension}")

    def parse_file(self, file_path: str) -> tuple[Tree, Query]:
        """Validate and parse a single source file into a syntax tree."""
        self.validate_file(file_path)

        if is_file_empty(file_path):
            raise ValueError(f"File is empty: {file_path}")

        if is_file_oversized(file_path, MAX_FILE_SIZE_MB_FOR_PARSING):
            raise ValueError(
                f"File exceeds max size of {MAX_FILE_SIZE_MB_FOR_PARSING}MB: {file_path}"
            )

        with open(file_path, "rb") as f:
            content = f.read()

        if is_file_binary(content):
            raise ValueError(f"File is binary: {file_path}")

        if is_file_minified(file_path, content):
            raise ValueError(f"File is minified: {file_path}")

        lang_config = self.get_language_config(Path(file_path).suffix)
        if lang_config is None:
            raise RuntimeError(f"Unexpected missing language config for {file_path}")        
        parser = Parser(lang_config.language)
        tree = parser.parse(content)
        return tree, lang_config.query