from api.message_router import extract_business_name


def test_plain_business_name_is_preserved() -> None:
    assert extract_business_name("文章牛肉湯") == "文章牛肉湯"


def test_command_wrappers_are_removed() -> None:
    assert extract_business_name("幫我查詢 文章牛肉湯 的網路評價報告") == "文章牛肉湯"


def test_generic_command_has_no_business_name() -> None:
    assert extract_business_name("查詢最新評價") is None
