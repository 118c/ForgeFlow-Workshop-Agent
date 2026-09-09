"""MES/WMS/EAM/HR/QMS 防腐层；内置基线与真实接口实现同一协议。"""

import asyncio
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import httpx
from pydantic import ValidationError

from ..core.config import get_settings
from ..integrations.contracts import (
    ManualPlanReference,
    MaterialReadiness,
    QualityConstraint,
    SourceMetadata,
    ToolingResource,
    ValidationDataSnapshot,
)
from ..models.schemas import DeviceResource, PlanVersionMetrics, SchedulingRequest, ShiftResource, WorkOrder


class BusinessGatewayError(RuntimeError):
    pass


class WorkshopGateway(ABC):
    @abstractmethod
    async def get_devices(self, factory_id: str, workshop_id: str) -> List[DeviceResource]: ...

    @abstractmethod
    async def get_shifts(self, factory_id: str, workshop_id: str, production_date: str, shift_codes: List[str]) -> List[ShiftResource]: ...

    @abstractmethod
    async def get_work_orders(self, request: SchedulingRequest) -> List[WorkOrder]: ...

    @abstractmethod
    async def collect_validation_snapshot(self, request: SchedulingRequest) -> ValidationDataSnapshot: ...

    @abstractmethod
    async def publish_plan(self, task_id: str, plan: Dict[str, Any]) -> Dict[str, Any]: ...


class MockWorkshopGateway(WorkshopGateway):
    """稳定、可重复的本地基线资料适配器。"""

    async def _latency(self) -> None:
        await asyncio.sleep(get_settings().mock_latency_ms / 1000.0)

    async def get_devices(self, factory_id: str, workshop_id: str) -> List[DeviceResource]:
        await self._latency()
        return [
            DeviceResource(device_id="AOI-01", name="3D AOI 光学检测机", line_code="DIP-01", station_code="S-AOI", capability=["测试"], oee=0.93, capacity_per_hour=150),
            DeviceResource(device_id="ASM-07", name="柔性装配单元 07", line_code="DIP-01", station_code="S-ASM-1", capability=["组装"], oee=0.89, capacity_per_hour=110),
            DeviceResource(device_id="ASM-12", name="柔性装配单元 12", line_code="DIP-02", station_code="S-ASM-2", capability=["组装"], oee=0.84, capacity_per_hour=92, next_maintenance_at="2026-09-10T18:30:00+08:00"),
            DeviceResource(device_id="ICT-03", name="ICT 在线测试台", line_code="DIP-02", station_code="S-ICT", capability=["测试"], oee=0.91, capacity_per_hour=130),
            DeviceResource(device_id="PKG-04", name="自动包装线 04", line_code="DIP-01", station_code="S-PKG", capability=["包装"], oee=0.87, capacity_per_hour=180),
            DeviceResource(device_id="PKG-06", name="自动包装线 06", line_code="DIP-02", station_code="S-PKG-2", capability=["包装"], status="maintenance", oee=0.0, capacity_per_hour=180),
        ]

    async def get_shifts(self, factory_id: str, workshop_id: str, production_date: str, shift_codes: List[str]) -> List[ShiftResource]:
        await self._latency()
        shifts = {
            "DAY": ShiftResource(shift_code="DAY", team_id="T-A", team_name="甲班", start_at=production_date + "T08:00:00+08:00", end_at=production_date + "T20:00:00+08:00", headcount=18, skill_tags=["组装", "测试", "包装"], attendance_rate=0.94),
            "NIGHT": ShiftResource(shift_code="NIGHT", team_id="T-B", team_name="乙班", start_at=production_date + "T20:00:00+08:00", end_at=production_date + "T23:59:59+08:00", headcount=15, skill_tags=["组装", "测试", "包装"], attendance_rate=0.88),
        }
        return [shifts[code] for code in shift_codes if code in shifts]

    async def get_work_orders(self, request: SchedulingRequest) -> List[WorkOrder]:
        await self._latency()
        return sorted(request.orders, key=lambda item: (-item.priority, item.due_at, item.order_id))

    async def collect_validation_snapshot(self, request: SchedulingRequest) -> ValidationDataSnapshot:
        now = datetime.now(timezone.utc)
        orders, devices, shifts = await asyncio.gather(
            self.get_work_orders(request), self.get_devices(request.factory_id, request.workshop_id),
            self.get_shifts(request.factory_id, request.workshop_id, request.production_date, request.shift_codes),
        )
        sources = {system: SourceMetadata(system=system, source_version="%s-BASELINE-1" % system, captured_at=now) for system in ("MES", "WMS", "EAM", "HR", "QMS")}
        materials = [MaterialReadiness(order_id=o.order_id, material_code="KIT-%s" % o.product_code, required_quantity=o.quantity, available_quantity=o.quantity, ready_at=now, lot_codes=["LOT-%s" % o.order_id[-3:]]) for o in orders]
        tooling = [ToolingResource(tool_id="FIX-%02d" % (i + 1), name="%s 共用治具" % o.product_code, compatible_products=[o.product_code]) for i, o in enumerate(orders)]
        quality = [QualityConstraint(product_code=o.product_code, quality_status="released", first_article_required=True, inspection_minutes=15) for o in orders]
        manual = ManualPlanReference(reference_id="MAN-%s-%s" % (request.workshop_id, request.production_date.replace("-", "")), workshop_id=request.workshop_id, production_date=request.production_date, metrics=PlanVersionMetrics(planned_quantity=sum(o.quantity for o in orders), average_utilization=0.82, risk_count=2, overtime_minutes=45, changeover_count=max(0, len(orders) - 1), on_time_rate=0.9))
        return ValidationDataSnapshot(snapshot_id="VS-%s" % uuid.uuid4().hex[:12].upper(), captured_at=now, sources=sources, work_orders=orders, devices=devices, shifts=shifts, materials=materials, tooling=tooling, quality_constraints=quality, manual_plan=manual)

    async def publish_plan(self, task_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        await self._latency()
        return {"accepted": True, "external_plan_id": "MES-%s" % task_id[-8:], "mode": "local"}


class HttpWorkshopGateway(WorkshopGateway):
    """企业 API 网关实现；所有读取都要求带版本与采集时间的信封。"""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.business_api_base_url or not settings.business_api_key:
            raise BusinessGatewayError("真实业务模式需要配置 BUSINESS_API_BASE_URL 与 BUSINESS_API_KEY")
        self.base_url = settings.business_api_base_url.rstrip("/")
        self.timeout = settings.business_api_timeout_seconds
        self.headers = {"Authorization": "Bearer %s" % settings.business_api_key, "X-Client-System": "forgeflow-agent"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                response = await client.request(method, self.base_url + path, **kwargs)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BusinessGatewayError("业务接口 %s 调用失败: %s" % (path, exc)) from exc

    async def _read_envelope(self, system: str, path: str, **kwargs: Any) -> Tuple[SourceMetadata, Any]:
        payload = await self._request("GET", path, **kwargs)
        try:
            metadata = SourceMetadata(system=system, source_version=payload["source_version"], captured_at=payload["captured_at"])
            return metadata, payload["data"]
        except (KeyError, TypeError, ValidationError) as exc:
            raise BusinessGatewayError("%s 回应不符合版本化资料信封契约" % system) from exc

    async def get_devices(self, factory_id: str, workshop_id: str) -> List[DeviceResource]:
        _, data = await self._read_envelope("EAM", "/v1/eam/equipment", params={"factory_id": factory_id, "workshop_id": workshop_id})
        return [DeviceResource.model_validate(item) for item in data]

    async def get_shifts(self, factory_id: str, workshop_id: str, production_date: str, shift_codes: List[str]) -> List[ShiftResource]:
        _, data = await self._read_envelope("HR", "/v1/hr/shifts", params={"factory_id": factory_id, "workshop_id": workshop_id, "date": production_date, "shift_codes": ",".join(shift_codes)})
        return [ShiftResource.model_validate(item) for item in data]

    async def get_work_orders(self, request: SchedulingRequest) -> List[WorkOrder]:
        _, data = await self._read_envelope("MES", "/v1/mes/work-orders", params={"workshop_id": request.workshop_id, "date": request.production_date})
        return [WorkOrder.model_validate(item) for item in data]

    async def collect_validation_snapshot(self, request: SchedulingRequest) -> ValidationDataSnapshot:
        params = {"factory_id": request.factory_id, "workshop_id": request.workshop_id, "date": request.production_date}
        responses = await asyncio.gather(
            self._read_envelope("MES", "/v1/mes/work-orders", params=params), self._read_envelope("WMS", "/v1/wms/material-readiness", params=params),
            self._read_envelope("EAM", "/v1/eam/equipment", params=params), self._read_envelope("EAM", "/v1/eam/tooling", params=params),
            self._read_envelope("HR", "/v1/hr/shifts", params=params), self._read_envelope("QMS", "/v1/qms/quality-constraints", params=params),
            self._read_envelope("MES", "/v1/mes/manual-plans", params=params),
        )
        (mes_orders, orders), (wms, materials), (eam_equipment, devices), (eam_tooling, tooling), (hr, shifts), (qms, quality), (mes_manual, manual) = responses
        mes = SourceMetadata(system="MES", source_version="%s|%s" % (mes_orders.source_version, mes_manual.source_version), captured_at=min(mes_orders.captured_at, mes_manual.captured_at))
        eam = SourceMetadata(system="EAM", source_version="%s|%s" % (eam_equipment.source_version, eam_tooling.source_version), captured_at=min(eam_equipment.captured_at, eam_tooling.captured_at))
        return ValidationDataSnapshot(
            snapshot_id="VS-%s" % uuid.uuid4().hex[:12].upper(), sources={item.system: item for item in (mes, wms, eam, hr, qms)},
            work_orders=[WorkOrder.model_validate(item) for item in orders], materials=[MaterialReadiness.model_validate(item) for item in materials],
            devices=[DeviceResource.model_validate(item) for item in devices], tooling=[ToolingResource.model_validate(item) for item in tooling],
            shifts=[ShiftResource.model_validate(item) for item in shifts], quality_constraints=[QualityConstraint.model_validate(item) for item in quality],
            manual_plan=ManualPlanReference.model_validate(manual) if manual else None,
        )

    async def publish_plan(self, task_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        payload = await self._request("POST", "/v1/mes/schedule-plans", json={"task_id": task_id, "plan": plan}, headers={"Idempotency-Key": task_id})
        return payload.get("data", payload)


_gateways: Dict[str, WorkshopGateway] = {"mock": MockWorkshopGateway()}


def get_workshop_gateway(data_source: str) -> WorkshopGateway:
    if data_source == "mock":
        return _gateways["mock"]
    if "real" not in _gateways:
        _gateways["real"] = HttpWorkshopGateway()
    return _gateways["real"]
