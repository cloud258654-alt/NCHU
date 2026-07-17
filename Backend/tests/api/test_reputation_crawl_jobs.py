import asyncio

import pytest

from api.reputation_crawl import (
    ReputationCrawlJobService,
    ReputationCrawlResult,
)


class FakeTaskRepository:
    def __init__(self):
        self.jobs = {}
        self.created = 0

    def find_reputation_job(self, *, line_user_id, source_message_id=None, active_only=False):
        candidates = [
            job for job in self.jobs.values()
            if job["line_user_id"] == line_user_id
            and (not source_message_id or job["config"].get("source_message_id") == source_message_id)
            and (not active_only or job["status"] in {"pending", "running"})
        ]
        return dict(candidates[-1]) if candidates else None

    def create(self, *, business_name, line_user_id, source_message_id, request_payload, **kwargs):
        self.created += 1
        task_id = str(self.created)
        self.jobs[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "business_name": business_name,
            "line_user_id": line_user_id,
            "config": {**request_payload, "source_message_id": source_message_id},
        }
        return task_id

    def get_reputation_job(self, task_id, *, line_user_id=None):
        job = self.jobs.get(str(task_id))
        if job is None or (line_user_id and job["line_user_id"] != line_user_id):
            return None
        return dict(job)

    def get_reputation_job_status(self, task_id, *, line_user_id=None):
        job = self.get_reputation_job(task_id, line_user_id=line_user_id)
        if job is None:
            return None
        return {
            **job,
            "ready": job["status"] in {"completed", "failed", "cancelled"},
            "platform_results": [],
            "articles_found": 0,
            "comments_found": 0,
            "error_message": job["config"].get("last_error"),
        }

    def mark_running(self, task_id):
        self.jobs[str(task_id)]["status"] = "running"

    def claim_pending(self, task_id):
        job = self.jobs[str(task_id)]
        if job["status"] != "pending":
            return False
        job["status"] = "running"
        return True

    def mark_failed(self, task_id, message):
        self.jobs[str(task_id)]["status"] = "failed"
        self.jobs[str(task_id)]["config"]["last_error"] = message


class FakeCrawler:
    _keyword = "店家特色"
    _platform = "all"
    _lookback_days = 0
    _max_results = 50
    _browser_concurrency = 2
    _persistence_grace_seconds = 30.0

    def __init__(self, repository, *, gate=None):
        self.repository = repository
        self.gate = gate
        self.calls = 0
        self.active = 0
        self.max_active = 0

    async def crawl(self, *, business_name, line_user_id, service_task_id, source_message_id):
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self.gate is not None:
            await self.gate.wait()
        await asyncio.sleep(0.01)
        self.active -= 1
        self.repository.jobs[service_task_id]["status"] = "completed"
        return ReputationCrawlResult(
            status="success",
            business_name=business_name,
            duration_seconds=0.01,
            task_id=service_task_id,
        )


@pytest.mark.asyncio
async def test_duplicate_webhook_event_reuses_the_same_job():
    repository = FakeTaskRepository()
    service = ReputationCrawlJobService(FakeCrawler(repository), repository)

    first = await service.create_job(
        business_name="Demo Shop", line_user_id="U1", source_message_id="evt-1"
    )
    second = await service.create_job(
        business_name="Demo Shop", line_user_id="U1", source_message_id="evt-1"
    )

    assert first["task_id"] == second["task_id"]
    assert second["reused"] is True
    assert repository.created == 1


@pytest.mark.asyncio
async def test_duplicate_run_does_not_start_a_second_crawler():
    repository = FakeTaskRepository()
    gate = asyncio.Event()
    crawler = FakeCrawler(repository, gate=gate)
    service = ReputationCrawlJobService(crawler, repository)
    created = await service.create_job(
        business_name="Demo Shop", line_user_id="U1", source_message_id="evt-1"
    )

    first = asyncio.create_task(service.run_job(created["task_id"]))
    while crawler.calls == 0:
        await asyncio.sleep(0)
    duplicate = await service.run_job(created["task_id"])
    gate.set()
    completed = await first

    assert duplicate["already_running"] is True
    assert completed["status"] == "completed"
    assert crawler.calls == 1


@pytest.mark.asyncio
async def test_persisted_running_job_is_not_started_again():
    repository = FakeTaskRepository()
    crawler = FakeCrawler(repository)
    service = ReputationCrawlJobService(crawler, repository)
    task_id = repository.create(
        business_name="Demo Shop",
        line_user_id="U1",
        source_message_id="evt-1",
        request_payload={},
    )
    repository.jobs[task_id]["status"] = "running"

    status = await service.run_job(task_id)

    assert status["already_running"] is True
    assert crawler.calls == 0


@pytest.mark.asyncio
async def test_status_enforces_line_user_ownership():
    repository = FakeTaskRepository()
    service = ReputationCrawlJobService(FakeCrawler(repository), repository)
    created = await service.create_job(
        business_name="Demo Shop", line_user_id="owner", source_message_id="evt-1"
    )

    with pytest.raises(KeyError):
        await service.status(created["task_id"], line_user_id="other-user")


@pytest.mark.asyncio
async def test_backend_instance_admits_only_one_full_business_job():
    repository = FakeTaskRepository()
    crawler = FakeCrawler(repository)
    service = ReputationCrawlJobService(crawler, repository, max_active_jobs=1)
    first_id = repository.create(
        business_name="Shop A", line_user_id="U1", source_message_id="evt-1", request_payload={}
    )
    second_id = repository.create(
        business_name="Shop B", line_user_id="U2", source_message_id="evt-2", request_payload={}
    )

    await asyncio.gather(service.run_job(first_id), service.run_job(second_id))

    assert crawler.calls == 2
    assert crawler.max_active == 1


@pytest.mark.asyncio
async def test_atomic_claim_prevents_two_service_instances_from_running_same_job():
    repository = FakeTaskRepository()
    gate = asyncio.Event()
    crawler = FakeCrawler(repository, gate=gate)
    first_service = ReputationCrawlJobService(crawler, repository)
    second_service = ReputationCrawlJobService(crawler, repository)
    task_id = repository.create(
        business_name="Shop A",
        line_user_id="U1",
        source_message_id="evt-1",
        request_payload={},
    )

    first = asyncio.create_task(first_service.run_job(task_id))
    while crawler.calls == 0:
        await asyncio.sleep(0)
    duplicate = await second_service.run_job(task_id)
    gate.set()
    await first

    assert duplicate["already_running"] is True
    assert crawler.calls == 1
