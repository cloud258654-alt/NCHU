from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_removed_obsolete_runtime_trees():
    removed_paths = [
        "legacy",
        "scripts/legacy_crawlers",
        "scripts/test_detail_comments.py",
        "scripts/verify_jsonl.py",
        "scripts/verify_major_platforms_supabase_ingestion.py",
        "scripts/verify_ptt_supabase_ingestion.py",
        "scripts/verify_threads_supabase_ingestion.py",
        "src",
        "sql/migrations",
        "ai",
        "jobs",
        "dashboard",
        "storage",
        "jobs/worker.py",
        "jobs/scheduler.py",
        "AGENT_HANDOFF.md",
        "Schema_overview.png",
        "docs/platforms",
        "docs/roadmap",
        "login.py",
        "adapters/dcard",
        "adapters/douyin",
        "adapters/facebook",
        "adapters/facebook_group",
        "adapters/instagram",
        "adapters/rednote",
        "adapters/search",
        "adapters/tiktok",
        "adapters/youtube",
    ]

    for relative_path in removed_paths:
        assert not (ROOT / relative_path).exists()


def test_no_root_level_platform_adapter_modules():
    assert not list((ROOT / "adapters").glob("*_adapter.py"))


def test_platform_packages_are_the_crawler_boundary():
    platform_dirs = [
        path
        for path in (ROOT / "adapters").iterdir()
        if path.is_dir() and not path.name.startswith("__")
    ]

    assert {path.name for path in platform_dirs} == {"google_maps", "ptt", "threads", "web"}
    for platform_dir in platform_dirs:
        if platform_dir.name == "web":
            assert ((platform_dir / "crawl4ai_crawler.py").exists()
                    or (platform_dir / "crawler.py").exists()), platform_dir
        else:
            assert (platform_dir / "crawler.py").exists(), platform_dir


def test_runner_is_the_single_crawler_entry_point():
    assert (ROOT / "runner.py").exists()
    assert not (ROOT / "src" / "main.py").exists()


def test_legacy_main_is_only_a_canonical_api_compatibility_shim():
    source = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "from api.main import app" in source
    assert "run_crawler_pipeline" not in source
    assert "文章牛肉湯" not in source


def test_design_reference_files_are_retained_but_not_runtime_inputs():
    project_root = ROOT.parent

    assert (project_root / "docs" / "design" / "Schema_overview.png").exists()
    assert (project_root / "docs" / "design" / "Frontend.html").exists()


def test_required_agent_handoff_documents_exist():
    project_root = ROOT.parent
    assert (project_root / "docs" / "AGENT_HANDOFF.md").exists()
    assert (project_root / "docs" / "architecture_review.md").exists()
    assert (project_root / "docs" / "database_execution_runbook.md").exists()


def test_removed_stale_project_documents():
    project_root = ROOT.parent
    removed_paths = [
        "docs/PHASE7A_PTT_GLOBAL_CRAWLER_REPORT.md",
        "docs/PHASE_THREADS_CRAWLER_REPAIR_REPORT.md",
        "docs/SEARCH_AGGREGATOR.md",
        "docs/schema_infographic.html",
        "docs/schema_infographic.infographic",
        "docs/schema_infographic.svg",
    ]

    for relative_path in removed_paths:
        assert not (project_root / relative_path).exists()
