import pytest

from app.models.schemas import DataSource, ReviewRequest, SchedulingRequest, TaskStatus
from app.repositories.task_repository import TaskRepository, VersionConflictError
from app.services.scheduling_service import SchedulingService
from app.services.workbench_service import list_plan_versions, read_resource_snapshot


@pytest.mark.asyncio
async def test_mock_pipeline_runs_five_nodes_and_waits_for_review(tmp_path):
    repository = TaskRepository(str(tmp_path / "tasks.db"))
    snapshot = await SchedulingService(repository).run(SchedulingRequest())

    assert snapshot.status == TaskStatus.NEED_REVIEW
    assert [step.node for step in snapshot.steps] == [
        "device_resource",
        "shift_query",
        "station_assign",
        "plan_generate",
        "human_review",
    ]
    assert snapshot.plan is not None
    assert len(snapshot.plan.assignments) == 6
    assert snapshot.plan.generated_by == "ortools-cp-sat"
    assert snapshot.plan.solver_metadata["status"] in {"OPTIMAL", "FEASIBLE"}
    assert {item.tool_id for item in snapshot.plan.assignments if item.process == "组装"}


@pytest.mark.asyncio
async def test_approve_publishes_plan_and_persists_audit(tmp_path):
    repository = TaskRepository(str(tmp_path / "tasks.db"))
    service = SchedulingService(repository)
    snapshot = await service.run(SchedulingRequest())
    approved = await service.review(
        snapshot.task_id,
        ReviewRequest(action="approve", reviewer="QA", expected_version=snapshot.version),
    )

    assert approved.status == TaskStatus.APPROVED
    assert approved.reviews[0].reviewer == "QA"
    assert any("MES 下发回执" in item for item in approved.warnings)


def test_repository_uses_optimistic_lock(tmp_path):
    repository = TaskRepository(str(tmp_path / "tasks.db"))
    request = SchedulingRequest()
    service = SchedulingService(repository)
    state = service._initial_state(request, "task-lock", "trace-lock")
    snapshot = repository.save(service._snapshot(state))
    repository.save(snapshot, expected_version=1)

    with pytest.raises(VersionConflictError):
        repository.save(snapshot, expected_version=1)


@pytest.mark.asyncio
async def test_resource_snapshot_has_traceable_source_and_capacity():
    snapshot = await read_resource_snapshot("FOX-SZ-01", "DIP-A", "2026-09-10", DataSource.MOCK)

    assert snapshot.source_version.startswith("RS-")
    assert len(snapshot.devices) == 6
    assert sum(shift.headcount for shift in snapshot.shifts) == 33
    assert any(device.status == "maintenance" for device in snapshot.devices)


@pytest.mark.asyncio
async def test_plan_version_history_keeps_material_plan_changes(tmp_path):
    repository = TaskRepository(str(tmp_path / "tasks.db"))
    service = SchedulingService(repository)
    original = await service.run(SchedulingRequest())
    await service.review(
        original.task_id,
        ReviewRequest(
            action="modify",
            reviewer="IE-01",
            expected_version=original.version,
            modifications={"title": "負載平衡修訂", "summary": {"average_utilization": 0.72}},
        ),
    )

    versions = list_plan_versions(task_id=original.task_id, repository=repository)
    assert len(versions) == 2
    assert versions[0].metrics.average_utilization == 0.72
    assert versions[1].metrics.average_utilization != 0.72
