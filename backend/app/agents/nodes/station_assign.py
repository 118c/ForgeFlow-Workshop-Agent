import time
from typing import Any, Dict

from ...services.constraint_solver import solve_workshop_schedule
from .common import finish_step


async def station_assign_node(state: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        assignments, solver_metadata = solve_workshop_schedule(state)
        update = finish_step(
            state,
            "station_assign",
            started,
            {
                "assignment_count": len(assignments),
                "solver": solver_metadata["engine"],
                "solver_status": solver_metadata["status"],
                "objective": solver_metadata["objective"],
                "wall_time_seconds": solver_metadata["wall_time_seconds"],
            },
        )
        update.update({"assignments": assignments, "solver_metadata": solver_metadata})
        return update
    except Exception as exc:
        update = finish_step(state, "station_assign", started, {"assignment_count": 0, "solver": "ortools-cp-sat"}, exc)
        update.update({"assignments": [], "solver_metadata": {"engine": "ortools-cp-sat", "status": "INFEASIBLE_OR_ERROR", "error": str(exc)}})
        return update
