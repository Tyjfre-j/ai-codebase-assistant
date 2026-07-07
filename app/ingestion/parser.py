
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_python as tspython
import tree_sitter_go as tsgo
import tree_sitter_typescript as tsts
import tree_sitter_javascript as tsjs
from tree_sitter import Language, Query, Parser, Tree

from app.ingestion.languages.python_queries import PYTHON_QUERY
from app.ingestion.languages.go_queries import GO_QUERY
from app.ingestion.languages.typescript_queries import TS_QUERY
from app.ingestion.languages.javascript_queries import JS_QUERY
from app.core.exceptions import (
    LanguageLoadError,
    TreeSitterParseError,
    UnsupportedFileExtensionError,
)


@dataclass
class LanguageConfig:
    name: str
    language: Language
    query: Query


@dataclass
class ParsedFile:
    tree: Tree
    query: Query
    language: str
    content: bytes


def load_languages() -> dict[str, LanguageConfig]:
    """Load all supported tree-sitter grammars and compile their queries."""
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
            raise LanguageLoadError(f"Failed to load language for extension {ext}: {e}") from e
        configs[ext] = LanguageConfig(name=name, language=lang, query=query)
    return configs


class CodeParser:
    def __init__(self):
        self.language_configs = load_languages()

    def get_language_config(self, file_extension: str) -> LanguageConfig | None:
        return self.language_configs.get(file_extension)

    def validate_file(self, file_path: str) -> None:
        """Raise UnsupportedFileExtensionError if the extension isn't supported."""
        file_extension = Path(file_path).suffix
        if file_extension not in self.language_configs:
            raise UnsupportedFileExtensionError(f"Unsupported file extension: {file_extension}")

    def parse_file(self, file_path: str, content: bytes) -> ParsedFile:
        """Parse raw file content into a tree-sitter tree."""
        self.validate_file(file_path)

        lang_config = self.get_language_config(Path(file_path).suffix)
        if lang_config is None:
            raise RuntimeError(f"Unexpected missing language config for {file_path}")

        try:
            tree = Parser(lang_config.language).parse(content)
        except Exception as e:
            raise TreeSitterParseError(f"Tree-sitter failed to parse {file_path}: {e}") from e

        return ParsedFile(
            tree=tree,
            query=lang_config.query,
            language=lang_config.name,
            content=content,
        )