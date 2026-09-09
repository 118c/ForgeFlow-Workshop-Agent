import time
from typing import Any, Dict

from .common import finish_step


async def human_review_node(state: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    required = bool(state["request"].get("require_human_review", True))
    update = finish_step(
        state,
        "human_review",
        started,
        {"review_required": required, "checkpoint": "durable"},
    )
    update.update(
        {
            "need_human_review": required,
            "status": "need_review" if required else "approved",
        }
    )
    return update
