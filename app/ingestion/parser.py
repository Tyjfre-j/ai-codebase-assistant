
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_go as tsgo
import tree_sitter_javascript as tsjs
import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser, Query, Tree

from app.core.exceptions import (
    LanguageLoadError,
    TreeSitterParseError,
    UnsupportedFileExtensionError,
)
from app.ingestion.languages import LANG_HELPERS

@dataclass(frozen=True)
class LanguageConfig:
    name: str
    language: Language
    parser: Parser
    query: Query


@dataclass(frozen=True)
class ParsedFile:
    tree: Tree
    query: Query
    language: str
    content: bytes


def load_languages() -> dict[str, LanguageConfig]:
    """Load all supported tree-sitter grammars and compile their queries."""
    specs = [
        # (extension, name, loader_function, query_string)
        (".py", "python", tspython.language, LANG_HELPERS["python"].QUERY),
        (".go", "go", tsgo.language, LANG_HELPERS["go"].QUERY),
        (".ts", "typescript", tsts.language_typescript, LANG_HELPERS["typescript"].QUERY),
        (".js", "javascript", tsjs.language, LANG_HELPERS["javascript"].QUERY),
    ]
    configs: dict[str, LanguageConfig] = {}
    for ext, name, loader_fn, query_str in specs:
        try:
            lang = Language(loader_fn())
            parser = Parser(lang)
            query = Query(lang, query_str)
        except Exception as e:
            raise LanguageLoadError(f"Failed to load language for extension {ext}: {e}") from e
        configs[ext] = LanguageConfig(name=name, language=lang, parser=parser, query=query)
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
            tree = lang_config.parser.parse(content)
        except Exception as e:
            raise TreeSitterParseError(f"Tree-sitter failed to parse {file_path}: {e}") from e

        return ParsedFile(
            tree=tree,
            query=lang_config.query,
            language=lang_config.name,
            content=content,
        )