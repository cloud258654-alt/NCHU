from core.search_models import build_search_query


def test_query_builder_with_site():
    assert build_search_query("文章牛肉湯", "ptt.cc") == "文章牛肉湯 site:ptt.cc"


def test_query_builder_without_site():
    assert build_search_query("文章牛肉湯") == "文章牛肉湯"

