"""车间作业规划 API。"""

import json
from typing import AsyncIterator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ...models.schemas import DataSource, PlanVersion, ResourceSnapshot, ReviewRequest, SchedulingRequest, TaskSnapshot
from ...repositories.task_repository import VersionConflictError, get_task_repository
from ...services.scheduling_service import SchedulingService, get_scheduling_service
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
