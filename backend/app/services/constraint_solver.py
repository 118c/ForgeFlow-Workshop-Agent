"""基于 OR-Tools CP-SAT 的车间约束排程器。"""

import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from ortools.sat.python import cp_model

from ..core.config import get_settings
from ..models.schemas import StationAssignment


class ConstraintInfeasibleError(RuntimeError):
    pass


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _minutes(value: str, base: datetime) -> int:
    return int((_dt(value) - base).total_seconds() // 60)


def solve_workshop_schedule(state: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """建立替代设备区间、班组技能、物料、治具、换线和维护窗口约束。"""
    settings = get_settings()
    orders = state.get("work_orders", [])
    devices = [item for item in state.get("devices", []) if item.get("status") == "available"]
    shifts = [item for item in state.get("shifts", []) if item.get("headcount", 0) > 0]
    materials = {item["order_id"]: item for item in state.get("materials", [])}
    tooling = state.get("tooling", [])
    quality = {item["product_code"]: item for item in state.get("quality_constraints", [])}
    if not orders or not devices or not shifts:
        raise ConstraintInfeasibleError("工单、设备或班组资料不完整")
    if not tooling:
        raise ConstraintInfeasibleError("EAM 治具资料不完整")

    shortages = [o["order_id"] for o in orders if o["order_id"] not in materials or int(materials[o["order_id"]]["available_quantity"]) < int(materials[o["order_id"]]["required_quantity"])]
    if shortages:
        raise ConstraintInfeasibleError("物料未齐套: %s" % ", ".join(shortages))
    quality_blocks = [o["product_code"] for o in orders if o["product_code"] not in quality or quality[o["product_code"]].get("quality_status") != "released"]
    if quality_blocks:
        raise ConstraintInfeasibleError("QMS 尚未放行: %s" % ", ".join(quality_blocks))

    base = min(_dt(item["start_at"]) for item in shifts)
    horizon = max(_minutes(item["end_at"], base) for item in shifts)
    model = cp_model.CpModel()
    operation_start: Dict[Tuple[int, int], Any] = {}
    operation_end: Dict[Tuple[int, int], Any] = {}
    operation_duration: Dict[Tuple[int, int], Any] = {}
    operation_options: Dict[Tuple[int, int], List[Dict[str, Any]]] = defaultdict(list)
    device_intervals: Dict[str, List[Any]] = defaultdict(list)
    tool_intervals: Dict[str, List[Any]] = defaultdict(list)
    device_choice: Dict[Tuple[int, int, str], Any] = {}
    tool_choice: Dict[Tuple[int, int, str], Any] = {}

    for order_index, order in enumerate(orders):
        route = order.get("process_route") or ["组装", "测试", "包装"]
        for process_index, process in enumerate(route):
            key = (order_index, process_index)
            start = model.new_int_var(0, horizon, "start_%s_%s" % key)
            end = model.new_int_var(0, horizon, "end_%s_%s" % key)
            duration = model.new_int_var(1, horizon, "duration_%s_%s" % key)
            operation_start[key], operation_end[key], operation_duration[key] = start, end, duration
            options: List[Dict[str, Any]] = []
            for device in devices:
                if process not in device.get("capability", []):
                    continue
                duration_minutes = max(15, math.ceil(int(order["quantity"]) * 60 / int(device["capacity_per_hour"])))
                maintenance_limit = horizon
                if device.get("next_maintenance_at"):
                    maintenance_limit = min(horizon, _minutes(device["next_maintenance_at"], base))
                for shift in shifts:
                    if process not in shift.get("skill_tags", []):
                        continue
                    windows = device.get("calendar_windows") or [{"start_at": shift["start_at"], "end_at": shift["end_at"]}]
                    for window_index, window in enumerate(windows):
                        lower = max(0, _minutes(shift["start_at"], base), _minutes(window["start_at"], base))
                        upper = min(horizon, _minutes(shift["end_at"], base), _minutes(window["end_at"], base), maintenance_limit)
                        if lower + duration_minutes > upper:
                            continue
                        selected = model.new_bool_var("select_%s_%s_%s_%s_%s" % (order_index, process_index, device["device_id"], shift["shift_code"], window_index))
                        option_start = model.new_int_var(lower, upper - duration_minutes, "option_start_%s" % selected.name)
                        option_end = model.new_int_var(lower + duration_minutes, upper, "option_end_%s" % selected.name)
                        interval = model.new_optional_interval_var(option_start, duration_minutes, option_end, selected, "interval_%s" % selected.name)
                        model.add(start == option_start).only_enforce_if(selected)
                        model.add(end == option_end).only_enforce_if(selected)
                        model.add(duration == duration_minutes).only_enforce_if(selected)
                        option = {"selected": selected, "device": device, "shift": shift, "duration": duration_minutes}
                        options.append(option)
                        device_intervals[device["device_id"]].append(interval)
            if not options:
                raise ConstraintInfeasibleError("%s/%s 无满足设备日历与人员技能的资源组合" % (order["order_id"], process))
            model.add_exactly_one(item["selected"] for item in options)
            operation_options[key] = options
            for device in devices:
                matching = [item["selected"] for item in options if item["device"]["device_id"] == device["device_id"]]
                chosen = model.new_bool_var("device_%s_%s_%s" % (order_index, process_index, device["device_id"]))
                if matching:
                    model.add(chosen == sum(matching))
                else:
                    model.add(chosen == 0)
                device_choice[(order_index, process_index, device["device_id"])] = chosen

            required_tools = [item for item in tooling if order["product_code"] in item.get("compatible_products", []) and process in item.get("required_processes", ["组装"]) and item.get("status") == "available"]
            process_requires_tool = any(process in item.get("required_processes", ["组装"]) for item in tooling)
            if process_requires_tool:
                if not required_tools:
                    raise ConstraintInfeasibleError("%s/%s 无可用兼容治具" % (order["order_id"], process))
                selections = []
                for tool in required_tools:
                    selected = model.new_bool_var("tool_%s_%s_%s" % (order_index, process_index, tool["tool_id"]))
                    interval = model.new_optional_interval_var(start, duration, end, selected, "tool_interval_%s" % selected.name)
                    selections.append(selected)
                    tool_choice[(order_index, process_index, tool["tool_id"])] = selected
                    tool_intervals[tool["tool_id"]].append(interval)
                model.add_exactly_one(selections)

        # 流水生产允许转移批提前流入下制程，同时保持工艺启动顺序。
        for process_index in range(1, len(route)):
            previous = (order_index, process_index - 1)
            current = (order_index, process_index)
            transfer_quarter = model.new_int_var(0, horizon, "transfer_quarter_%s_%s" % current)
            transfer_lag = model.new_int_var(15, horizon, "transfer_%s_%s" % current)
            model.add_division_equality(transfer_quarter, operation_duration[previous], 4)
            model.add_max_equality(transfer_lag, [15, transfer_quarter])
            model.add(operation_start[current] >= operation_start[previous] + transfer_lag)

    for intervals in device_intervals.values():
        model.add_no_overlap(intervals)
    for intervals in tool_intervals.values():
        model.add_no_overlap(intervals)

    # 同设备不同产品必须保留换线窗口。
    for left_index, left in enumerate(orders):
        for right_index in range(left_index + 1, len(orders)):
            right = orders[right_index]
            if left["product_code"] == right["product_code"]:
                continue
            for left_process in range(len(left.get("process_route") or [])):
                for right_process in range(len(right.get("process_route") or [])):
                    for device in devices:
                        left_on = device_choice[(left_index, left_process, device["device_id"])]
                        right_on = device_choice[(right_index, right_process, device["device_id"])]
                        before = model.new_bool_var("before_%s_%s_%s_%s_%s" % (left_index, left_process, right_index, right_process, device["device_id"]))
                        model.add(operation_start[(right_index, right_process)] >= operation_end[(left_index, left_process)] + settings.changeover_minutes).only_enforce_if([left_on, right_on, before])
                        model.add(operation_start[(left_index, left_process)] >= operation_end[(right_index, right_process)] + settings.changeover_minutes).only_enforce_if([left_on, right_on, before.Not()])

    final_ends = [operation_end[(index, len(order.get("process_route") or []) - 1)] for index, order in enumerate(orders)]
    makespan = model.new_int_var(0, horizon, "makespan")
    model.add_max_equality(makespan, final_ends)
    weighted_starts = sum(operation_start[(i, 0)] * int(order.get("priority", 3)) for i, order in enumerate(orders))
    model.minimize(makespan * 100 + weighted_starts)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = settings.solver_time_limit_seconds
    solver.parameters.num_search_workers = settings.solver_workers
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise ConstraintInfeasibleError("CP-SAT 未找到可行方案，状态: %s" % solver.status_name(status))

    assignments: List[Dict[str, Any]] = []
    for order_index, order in enumerate(orders):
        route = order.get("process_route") or ["组装", "测试", "包装"]
        for process_index, process in enumerate(route):
            key = (order_index, process_index)
            option = next(item for item in operation_options[key] if solver.boolean_value(item["selected"]))
            selected_tool = next((tool_id for (oi, pi, tool_id), var in tool_choice.items() if oi == order_index and pi == process_index and solver.boolean_value(var)), None)
            start_minute, end_minute = solver.value(operation_start[key]), solver.value(operation_end[key])
            shift_minutes = max(1, _minutes(option["shift"]["end_at"], base) - _minutes(option["shift"]["start_at"], base))
            assignment = StationAssignment(
                assignment_id="ASG-%02d-%02d" % (order_index + 1, process_index + 1), order_id=order["order_id"], product_code=order["product_code"], process=process,
                station_code=option["device"]["station_code"], device_id=option["device"]["device_id"], shift_code=option["shift"]["shift_code"], team_name=option["shift"]["team_name"], tool_id=selected_tool,
                planned_quantity=order["quantity"], start_at=(base + timedelta(minutes=start_minute)).isoformat(), end_at=(base + timedelta(minutes=end_minute)).isoformat(), utilization=round(option["duration"] / shift_minutes, 4),
            )
            assignments.append(assignment.model_dump(mode="json"))
    metadata = {"engine": "ortools-cp-sat", "status": solver.status_name(status), "objective": solver.objective_value, "wall_time_seconds": round(solver.wall_time, 4), "conflicts": solver.num_conflicts, "branches": solver.num_branches, "constraints": ["material", "tooling", "changeover", "equipment_calendar", "workforce_skill", "process_precedence"]}
    return assignments, metadata
