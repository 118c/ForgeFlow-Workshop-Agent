import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from ...models.schemas import StationAssignment
from .common import finish_step


def _fallback_devices() -> List[Dict[str, Any]]:
    return [
        {"device_id": "SAFE-ASM", "station_code": "S-SAFE-ASM", "capability": ["组装"], "capacity_per_hour": 70, "status": "fallback"},
        {"device_id": "SAFE-TEST", "station_code": "S-SAFE-TEST", "capability": ["测试"], "capacity_per_hour": 90, "status": "fallback"},
        {"device_id": "SAFE-PKG", "station_code": "S-SAFE-PKG", "capability": ["包装"], "capacity_per_hour": 120, "status": "fallback"},
    ]


async def station_assign_node(state: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        devices = state.get("devices") or _fallback_devices()
        shifts = state.get("shifts") or [{"shift_code": "DAY", "team_name": "应急班组"}]
        orders = state.get("work_orders") or state["request"].get("orders", [])
        by_process = {
            process: [device for device in devices if process in device.get("capability", [])]
            for process in ("组装", "测试", "包装")
        }
        missing = [name for name, resources in by_process.items() if not resources]
        if missing:
            fallback = _fallback_devices()
            for process in missing:
                by_process[process] = [d for d in fallback if process in d["capability"]]

        base_time = datetime.fromisoformat(state["request"]["production_date"] + "T08:00:00+08:00")
        device_ready = {item["device_id"]: base_time for item in devices + _fallback_devices()}
        assignments = []
        for order_index, order in enumerate(orders):
            for process_index, process in enumerate(order.get("process_route") or ["组装", "测试", "包装"]):
                candidates = by_process.get(process) or _fallback_devices()
                device = candidates[(order_index + process_index) % len(candidates)]
                start_at = device_ready.get(device["device_id"], base_time)
                duration_hours = max(0.25, order["quantity"] / float(device["capacity_per_hour"]))
                end_at = start_at + timedelta(hours=duration_hours)
                device_ready[device["device_id"]] = end_at
                shift = shifts[0 if start_at.hour < 20 else min(1, len(shifts) - 1)]
                assignment = StationAssignment(
                    assignment_id="ASG-%02d-%02d" % (order_index + 1, process_index + 1),
                    order_id=order["order_id"],
                    product_code=order["product_code"],
                    process=process,
                    station_code=device["station_code"],
                    device_id=device["device_id"],
                    shift_code=shift["shift_code"],
                    team_name=shift["team_name"],
                    planned_quantity=order["quantity"],
                    start_at=start_at.isoformat(),
                    end_at=end_at.isoformat(),
                    utilization=min(1.5, duration_hours / 12.0),
                )
                assignments.append(assignment.model_dump(mode="json"))
        update = finish_step(
            state,
            "station_assign",
            started,
            {"assignment_count": len(assignments), "fallback_resources": not bool(state.get("devices"))},
        )
        update["assignments"] = assignments
        return update
    except Exception as exc:
        update = finish_step(state, "station_assign", started, {"assignment_count": 0}, exc)
        update["assignments"] = []
        return update

