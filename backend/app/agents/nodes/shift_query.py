import time
from typing import Any, Dict

from ...models.schemas import SchedulingRequest
from ..tools import get_toolset
from .common import finish_step


async def shift_query_node(state: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    request = SchedulingRequest.model_validate(state["request"])
    try:
        toolset = get_toolset(state["data_source"])
        planning_snapshot = await toolset.query_planning_snapshot(request)
        shifts = planning_snapshot["shifts"]
        orders = planning_snapshot["work_orders"]
        update = finish_step(
            state,
            "shift_query",
            started,
            {"shift_count": len(shifts), "headcount": sum(s["headcount"] for s in shifts), "order_count": len(orders)},
        )
        update.update({
            "devices": planning_snapshot["devices"],
            "shifts": shifts,
            "work_orders": orders,
            "materials": planning_snapshot["materials"],
            "tooling": planning_snapshot["tooling"],
            "quality_constraints": planning_snapshot["quality_constraints"],
        })
        return update
    except Exception as exc:
        update = finish_step(state, "shift_query", started, {"shift_count": 0}, exc)
        update.update({"shifts": [], "work_orders": [item.model_dump(mode="json") for item in request.orders], "materials": [], "tooling": [], "quality_constraints": []})
        return update
