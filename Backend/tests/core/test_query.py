from core.query import build_query_attempts, build_search_query, contains_business_name


def test_business_name_is_base_search_query_when_keyword_is_missing():
    assert build_search_query(business_name="文章牛肉湯", keyword=None) == "文章牛肉湯"


def test_keyword_is_optional_extra_search_intent():
    assert build_search_query(business_name="文章牛肉湯", keyword="牛肉湯") == "文章牛肉湯 牛肉湯"


def test_duplicate_keyword_is_not_repeated():
    assert build_search_query(business_name="文章牛肉湯", keyword="文章牛肉湯") == "文章牛肉湯"


def test_business_identity_match_ignores_case_space_and_punctuation():
    assert contains_business_name("Review: Example-Shop is good", "Example Shop")
    assert contains_business_name("文章 牛肉湯很好吃", "文章牛肉湯")
    assert not contains_business_name("Another Shop review", "Example Shop")


def test_query_attempts_are_bounded_and_fall_back_to_business():
    assert build_query_attempts(business_name="Example Shop", keyword="service") == [
        "Example Shop service",
        "Example Shop",
    ]


def test_business_only_query_ignores_optional_keyword():
    assert build_query_attempts(
        business_name="Example Shop",
        keyword="service",
        business_only=True,
    ) == ["Example Shop"]
