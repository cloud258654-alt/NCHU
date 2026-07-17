from core.search_config import SearchConfig
from core.search_engines import engine_names_for


def test_engine_names_auto_prefers_searxng_when_configured():
    config = SearchConfig(searxng_base_url="http://localhost:8080")

    assert engine_names_for("auto", config) == ["searxng", "duckduckgo", "bing"]


def test_engine_names_auto_falls_back_without_searxng():
    config = SearchConfig(searxng_base_url=None)

    assert engine_names_for("auto", config) == ["duckduckgo", "bing"]


def test_engine_names_all_keeps_searxng_first_when_available():
    config = SearchConfig(searxng_base_url="http://localhost:8080")

    assert engine_names_for("all", config) == ["searxng", "duckduckgo", "bing"]
