import os
import uuid

import pytest

from app.core.redis_runtime import RedisCoordinator
from app.integrations.contracts import ShadowRunRequest
from app.models.schemas import HistoricalReplayRequest, ReviewRequest, RolloutRollbackRequest, RolloutUpdate, SchedulingRequest
from app.repositories.task_repository import TaskRepository
from app.services.queue_service import submit_job
from app.services.constraint_solver import ConstraintInfeasibleError, solve_workshop_schedule
from app.services.business_gateway import MockWorkshopGateway
from app.services.replay_service import run_historical_replay
from app.services.rollout_service import may_publish, rollback_rollout_policy, update_rollout_policy
from app.services.scheduling_service import SchedulingService
from app.services.shadow_service import run_shadow_validation


@pytest.mark.asyncio
async def test_local_queue_is_idempotent_and_executes_inline(tmp_path):
    repository = TaskRepository(str(tmp_path / "queue.db"))
    key = "test-%s" % uuid.uuid4().hex
    first = await submit_job(SchedulingRequest(), key, repository)
    second = await submit_job(SchedulingRequest(), key, repository)
    assert first.job_id == second.job_id
    assert first.status.value == "succeeded"
    assert first.task_id


@pytest.mark.asyncio
async def test_shadow_run_validates_all_five_system_boundaries(tmp_path):
    repository = TaskRepository(str(tmp_path / "shadow.db"))
    task = await SchedulingService(repository).run(SchedulingRequest())
    report = await run_shadow_validation(ShadowRunRequest(task_id=task.task_id, data_source="mock"), repository)
    assert report.status == "passed"
    assert report.publish_blocked is True
    assert set(report.source_versions) == {"MES", "WMS", "EAM", "HR", "QMS"}
    assert len(report.checks) == 7
    assert repository.get_shadow_report(report.shadow_run_id, type(report)) is not None


@pytest.mark.asyncio
async def test_historical_replay_compares_manual_baseline_without_publish(tmp_path):
    repository = TaskRepository(str(tmp_path / "replay.db"))
    source = await SchedulingService(repository).run(SchedulingRequest())
    report = await run_historical_replay(HistoricalReplayRequest(source_task_id=source.task_id, data_source="mock"), repository)
    assert report.baseline_type == "manual_plan"
    assert report.publish_blocked is True
    assert repository.get_replay_report(report.replay_id) == report


def test_workshop_rollout_canary_and_one_click_rollback(tmp_path):
    repository = TaskRepository(str(tmp_path / "rollout.db"))
    shadow = update_rollout_policy("DIP-A", RolloutUpdate(mode="shadow", updated_by="ops", expected_version=0), repository)
    canary = update_rollout_policy("DIP-A", RolloutUpdate(mode="canary", traffic_percent=10, updated_by="ops", expected_version=shadow.version), repository)
    assert canary.traffic_percent == 10
    restored = rollback_rollout_policy("DIP-A", RolloutRollbackRequest(updated_by="ops", expected_version=canary.version), repository)
    assert restored.mode.value == "shadow"
    assert restored.version == 3
    assert may_publish("task-any", "DIP-A", repository) is False


@pytest.mark.asyncio
async def test_shadow_rollout_blocks_mes_outbox(tmp_path):
    repository = TaskRepository(str(tmp_path / "release-gate.db"))
    task = await SchedulingService(repository).run(SchedulingRequest())
    update_rollout_policy("DIP-A", RolloutUpdate(mode="shadow", updated_by="ops", expected_version=0), repository)
    approved = await SchedulingService(repository).review(task.task_id, ReviewRequest(action="approve", expected_version=task.version),)
    assert approved.status.value == "approved"
    assert any("发布策略未放行" in item for item in approved.warnings)
    assert repository.claim_outbox() == []


@pytest.mark.asyncio
async def test_cp_sat_rejects_material_shortage():
    request = SchedulingRequest()
    snapshot = await MockWorkshopGateway().collect_validation_snapshot(request)
    state = snapshot.model_dump(mode="json")
    state["materials"][0]["available_quantity"] = 0
    with pytest.raises(ConstraintInfeasibleError, match="物料未齐套"):
        solve_workshop_schedule(state)


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="需要 PostgreSQL 集成环境")
def test_postgres_repository_round_trip():
    repository = TaskRepository(os.environ["TEST_POSTGRES_URL"])
    repository.clear_all()
    service = SchedulingService(repository)
    state = service._initial_state(SchedulingRequest(), "task-pg", "trace-pg")
    saved = repository.save(service._snapshot(state))
    assert repository.get(saved.task_id) == saved


@pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"), reason="需要 Redis 集成环境")
def test_redis_coordination_round_trip():
    coordinator = RedisCoordinator(os.environ["TEST_REDIS_URL"], "forgeflow-ci")
    key = "test:%s" % uuid.uuid4().hex
    assert coordinator.ping()
    assert coordinator.set_json(key, {"ready": True}, ttl_seconds=30)
    assert coordinator.get_json(key) == {"ready": True}
    with coordinator.lock(key + ":lock", timeout=10):
        assert True
