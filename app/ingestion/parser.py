from dataclasses import dataclass

import tree_sitter_python as tspython
from tree_sitter import Language, Query

from app.ingestion.languages.python_queries import PYTHON_QUERY


@dataclass
class LanguageConfig:
    name: str
    language: Language
    query: Query


def load_languages() -> dict[str, LanguageConfig]:
    specs = [
        # (extension, name, loader_function, query_string)
        (".py", "python", tspython.language, PYTHON_QUERY),
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

if __name__ == "__main__":
    configs = load_languages()
    for ext, cfg in configs.items():
        print(ext, "->", cfg.name)