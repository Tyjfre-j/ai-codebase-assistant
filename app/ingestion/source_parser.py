from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language, Parser, Query, Tree

from app.core.exceptions import (
    LanguageLoadError,
    TreeSitterParseError,
    UnsupportedFileExtensionError,
)
from app.ingestion.languages import LANG_HELPERS


@dataclass(frozen=True)
class LanguageConfig:
    """Tree-sitter parser/query bundle for one file extension."""
    name: str
    language: Language
    parser: Parser
    query: Query
    ref_query: Query


@dataclass(frozen=True)
class ParsedFile:
    """Tree-sitter parse result plus the source bytes used to build it."""
    tree: Tree
    query: Query
    ref_query: Query
    language: str
    content: bytes


def load_languages() -> dict[str, LanguageConfig]:
    """Load all supported tree-sitter grammars and compile their queries."""
    configs: dict[str, LanguageConfig] = {}
    for name, module in LANG_HELPERS.items():
        try:
            lang = module.get_language()
            parser = Parser(lang)
            query = Query(lang, module.QUERY)
            ref_query = Query(lang, module.REF_QUERY)
        except Exception as e:
            raise LanguageLoadError(f"Failed to load language {name!r}: {e}") from e
        configs[module.FILE_EXTENSION] = LanguageConfig(
            name=name, language=lang, parser=parser, query=query, ref_query=ref_query
        )
    return configs


class CodeParser:
    """Parse supported source files with their language-specific queries."""

    def __init__(self) -> None:
        self.language_configs = load_languages()

    def get_language_config(self, file_extension: str) -> LanguageConfig | None:
        """Return the parser config for an extension, if supported."""
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
            ref_query=lang_config.ref_query,
            language=lang_config.name,
            content=content,
        )