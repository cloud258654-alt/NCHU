from scripts.verify_supabase_ingestion import _requires_data_yield


def test_requires_data_yield_uses_result_summary_when_available():
    assert _requires_data_yield(
        {
            "total_posts": 0,
            "total_comments": 0,
            "execution_config": {
                "result_summary": {
                    "outcome": "success_no_results",
                    "data_yield_success": False,
                }
            },
        }
    ) is False

    assert _requires_data_yield(
        {
            "total_posts": 0,
            "total_comments": 0,
            "execution_config": {
                "result_summary": {
                    "outcome": "success_with_data",
                    "data_yield_success": True,
                }
            },
        }
    ) is True


def test_requires_data_yield_falls_back_to_total_counts():
    assert _requires_data_yield({"total_posts": 1, "total_comments": 0, "execution_config": {}}) is True
    assert _requires_data_yield({"total_posts": 0, "total_comments": 0, "execution_config": {}}) is False
