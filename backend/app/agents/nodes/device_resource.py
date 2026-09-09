import time
from typing import Any, Dict

from ...models.schemas import SchedulingRequest
from ..tools import get_toolset
from .common import finish_step


async def device_resource_node(state: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    request = SchedulingRequest.model_validate(state["request"])
    try:
        devices = await get_toolset(state["data_source"]).query_available_devices(
            request.factory_id, request.workshop_id
        )
        available = [item for item in devices if item["status"] == "available"]
        update = finish_step(
            state,
            "device_resource",
            started,
            {"total": len(devices), "available": len(available), "source": state["data_source"]},
        )
        update["devices"] = available
        return update
    except Exception as exc:
        update = finish_step(state, "device_resource", started, {"available": 0}, exc)
        update["devices"] = []
        return update

