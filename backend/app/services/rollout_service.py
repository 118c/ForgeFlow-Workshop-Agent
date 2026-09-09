"""按车间隔离的灰度策略、发布门禁与版本回退。"""

import hashlib
from typing import Optional

from ..core.config import get_settings
from ..models.schemas import RolloutMode, RolloutPolicy, RolloutRollbackRequest, RolloutUpdate
from ..repositories.task_repository import TaskRepository, get_task_repository


def get_rollout_policy(workshop_id: str, repository: Optional[TaskRepository] = None) -> RolloutPolicy:
    repository = repository or get_task_repository()
    saved = repository.get_rollout_policy(workshop_id)
    if saved:
        return saved
    local = not get_settings().enterprise_mode
    return RolloutPolicy(workshop_id=workshop_id, mode=RolloutMode.ACTIVE if local else RolloutMode.SHADOW, traffic_percent=100 if local else 0, version=0, updated_by="system", reason="默认安全策略")


def update_rollout_policy(workshop_id: str, command: RolloutUpdate, repository: Optional[TaskRepository] = None) -> RolloutPolicy:
    repository = repository or get_task_repository()
    percent = command.traffic_percent
    if command.mode == RolloutMode.ACTIVE:
        percent = 100
    elif command.mode in (RolloutMode.SHADOW, RolloutMode.DISABLED):
        percent = 0
    elif not 1 <= percent <= 99:
        raise ValueError("canary 模式流量比例必须为 1-99")
    return repository.save_rollout_policy(RolloutPolicy(workshop_id=workshop_id, mode=command.mode, traffic_percent=percent, updated_by=command.updated_by, reason=command.reason), expected_version=command.expected_version)


def rollback_rollout_policy(workshop_id: str, command: RolloutRollbackRequest, repository: Optional[TaskRepository] = None) -> RolloutPolicy:
    repository = repository or get_task_repository()
    current = repository.get_rollout_policy(workshop_id)
    if not current:
        raise KeyError(workshop_id)
    if command.expected_version is not None and current.version != command.expected_version:
        from ..repositories.task_repository import VersionConflictError
        raise VersionConflictError("灰度策略版本已变化：期望 %s，当前 %s" % (command.expected_version, current.version))
    history = repository.list_rollout_history(workshop_id)
    previous = next((item for item in history if item.version < current.version), None)
    if not previous:
        raise ValueError("没有可回退的历史灰度策略")
    restored = previous.model_copy(update={"updated_by": command.updated_by, "reason": "%s；恢复 V%s" % (command.reason, previous.version)})
    return repository.save_rollout_policy(restored, expected_version=current.version)


def may_publish(task_id: str, workshop_id: str, repository: Optional[TaskRepository] = None) -> bool:
    policy = get_rollout_policy(workshop_id, repository)
    if policy.mode == RolloutMode.ACTIVE:
        return True
    if policy.mode != RolloutMode.CANARY:
        return False
    bucket = int(hashlib.sha256((workshop_id + ":" + task_id).encode("utf-8")).hexdigest()[:8], 16) % 100
    return bucket < policy.traffic_percent
