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
        shifts = await toolset.query_shift_roster(
            request.factory_id,
            request.workshop_id,
            request.production_date,
            request.shift_codes,
        )
        orders = await toolset.query_work_orders(request)
        update = finish_step(
            state,
            "shift_query",
            started,
            {"shift_count": len(shifts), "headcount": sum(s["headcount"] for s in shifts), "order_count": len(orders)},
        )
        update.update({"shifts": shifts, "work_orders": orders})
        return update
    except Exception as exc:
        update = finish_step(state, "shift_query", started, {"shift_count": 0}, exc)
        update.update({"shifts": [], "work_orders": [item.model_dump(mode="json") for item in request.orders]})
        return update

