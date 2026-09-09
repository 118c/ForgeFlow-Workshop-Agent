"""车间作业规划 API。"""

import json
from typing import AsyncIterator, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from ...integrations.contracts import ShadowRunReport, ShadowRunRequest
from ...models.schemas import DataSource, HistoricalReplayReport, HistoricalReplayRequest, PlanVersion, QueueJob, ResourceSnapshot, ReviewRequest, RolloutPolicy, RolloutRollbackRequest, RolloutUpdate, SchedulingRequest, TaskSnapshot
from ...repositories.task_repository import VersionConflictError, get_task_repository
from ...services.scheduling_service import SchedulingService, get_scheduling_service
from ...services.queue_service import submit_job
from ...services.replay_service import run_historical_replay
from ...services.rollout_service import get_rollout_policy, rollback_rollout_policy, update_rollout_policy
from ...services.shadow_service import run_shadow_validation
from ...services.workbench_service import list_plan_versions, read_resource_snapshot


router = APIRouter(prefix="/scheduling", tags=["车间作业规划"])
legacy_router = APIRouter(prefix="/trip", tags=["兼容接口"])


def _sse(payload: dict, event: str = "progress") -> str:
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(payload, ensure_ascii=False, default=str))


async def _event_stream(request: SchedulingRequest, service: SchedulingService) -> AsyncIterator[str]:
    try:
        async for event in service.stream(request):
            yield _sse(event.model_dump(mode="json"), "complete" if event.node == "complete" else "progress")
    except Exception as exc:
        yield _sse({"node": "error", "status": "failed", "message": str(exc)}, "error")


@router.post("/plan", response_model=TaskSnapshot)
async def create_plan(request: SchedulingRequest, service: SchedulingService = Depends(get_scheduling_service)):
    return await service.run(request)


@router.post("/jobs", response_model=QueueJob)
async def enqueue_plan(request: SchedulingRequest, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
    """提交可幂等的排程任务；企业模式由 Celery 异步执行。"""
    return await submit_job(request, idempotency_key)


@router.get("/jobs/{job_id}", response_model=QueueJob)
async def get_job(job_id: str):
    job = get_task_repository().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务队列记录不存在")
    return job


@router.post("/plan/stream")
async def create_plan_stream(request: SchedulingRequest, service: SchedulingService = Depends(get_scheduling_service)):
    return StreamingResponse(
        _event_stream(request, service),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@legacy_router.post("/plan/stream", include_in_schema=False)
async def legacy_plan_stream(request: SchedulingRequest, service: SchedulingService = Depends(get_scheduling_service)):
    """保留原 SSE URL，便于旧网关灰度迁移。"""
    return StreamingResponse(_event_stream(request, service), media_type="text/event-stream")


@router.get("/tasks/{task_id}", response_model=TaskSnapshot)
async def get_task(task_id: str):
    snapshot = get_task_repository().get(task_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="任务不存在")
    return snapshot


@router.get("/tasks", response_model=List[TaskSnapshot])
async def list_tasks(limit: int = Query(default=20, ge=1, le=100)):
    return get_task_repository().list_recent(limit)


@router.get("/resources", response_model=ResourceSnapshot)
async def get_resources(
    factory_id: str = Query(default="FOX-SZ-01"),
    workshop_id: str = Query(default="DIP-A"),
    production_date: str = Query(default="2026-09-10"),
    source: DataSource = Query(default=DataSource.MOCK),
):
    """读取一次带来源版本和采集时间的设备、班组资源快照。"""
    return await read_resource_snapshot(factory_id, workshop_id, production_date, source)


@router.get("/plans/versions", response_model=List[PlanVersion])
async def get_plan_versions(
    task_id: Optional[str] = Query(default=None),
    workshop_id: Optional[str] = Query(default=None),
    production_date: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
):
    """读取同一任务的历史修订，或同车间生产日的候选方案。"""
    return list_plan_versions(task_id, workshop_id, production_date, limit)


@router.post("/shadow-runs", response_model=ShadowRunReport)
async def create_shadow_run(command: ShadowRunRequest):
    """以真实或基线资料验证候选方案，固定禁止写回 MES。"""
    try:
        return await run_shadow_validation(command)
    except KeyError:
        raise HTTPException(status_code=404, detail="任务不存在或尚无候选方案")


@router.get("/shadow-runs/{shadow_run_id}", response_model=ShadowRunReport)
async def get_shadow_run(shadow_run_id: str):
    report = get_task_repository().get_shadow_report(shadow_run_id, ShadowRunReport)
    if not report:
        raise HTTPException(status_code=404, detail="影子验证记录不存在")
    return report


@router.post("/replays", response_model=HistoricalReplayReport)
async def create_replay(command: HistoricalReplayRequest):
    """使用历史工单重新求解，并与同期人工计划基准对照。"""
    try:
        return await run_historical_replay(command)
    except KeyError:
        raise HTTPException(status_code=404, detail="历史来源任务不存在或没有计划")


@router.get("/replays/{replay_id}", response_model=HistoricalReplayReport)
async def get_replay(replay_id: str):
    report = get_task_repository().get_replay_report(replay_id)
    if not report:
        raise HTTPException(status_code=404, detail="历史回放记录不存在")
    return report


@router.get("/rollouts/{workshop_id}", response_model=RolloutPolicy)
async def read_rollout(workshop_id: str):
    return get_rollout_policy(workshop_id)


@router.put("/rollouts/{workshop_id}", response_model=RolloutPolicy)
async def configure_rollout(workshop_id: str, command: RolloutUpdate):
    try:
        return update_rollout_policy(workshop_id, command)
    except VersionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/rollouts/{workshop_id}/history", response_model=List[RolloutPolicy])
async def read_rollout_history(workshop_id: str):
    return get_task_repository().list_rollout_history(workshop_id)


@router.post("/rollouts/{workshop_id}/rollback", response_model=RolloutPolicy)
async def rollback_rollout(workshop_id: str, command: RolloutRollbackRequest):
    try:
        return rollback_rollout_policy(workshop_id, command)
    except KeyError:
        raise HTTPException(status_code=404, detail="车间尚未建立灰度策略")
    except VersionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/tasks/{task_id}/review", response_model=TaskSnapshot)
async def review_task(task_id: str, command: ReviewRequest, service: SchedulingService = Depends(get_scheduling_service)):
    try:
        return await service.review(task_id, command)
    except KeyError:
        raise HTTPException(status_code=404, detail="任务不存在")
    except VersionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
