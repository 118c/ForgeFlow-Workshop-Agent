"""MES/WMS/HR 业务接口适配层。

Mock 和真实接口实现同一协议。切换 DATA_SOURCE 不会影响 Agent 节点。
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List

import httpx

from ..core.config import get_settings
from ..models.schemas import DeviceResource, SchedulingRequest, ShiftResource, WorkOrder


class BusinessGatewayError(RuntimeError):
    pass


class WorkshopGateway(ABC):
    @abstractmethod
    async def get_devices(self, factory_id: str, workshop_id: str) -> List[DeviceResource]:
        raise NotImplementedError

    @abstractmethod
    async def get_shifts(
        self, factory_id: str, workshop_id: str, production_date: str, shift_codes: List[str]
    ) -> List[ShiftResource]:
        raise NotImplementedError

    @abstractmethod
    async def get_work_orders(self, request: SchedulingRequest) -> List[WorkOrder]:
        raise NotImplementedError

    @abstractmethod
    async def publish_plan(self, task_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class MockWorkshopGateway(WorkshopGateway):
    """稳定、可重复的内置基线数据适配器。"""

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

    async def get_shifts(
        self, factory_id: str, workshop_id: str, production_date: str, shift_codes: List[str]
    ) -> List[ShiftResource]:
        await self._latency()
        shifts = {
            "DAY": ShiftResource(shift_code="DAY", team_id="T-A", team_name="甲班", start_at=production_date + "T08:00:00+08:00", end_at=production_date + "T20:00:00+08:00", headcount=18, skill_tags=["组装", "测试", "包装"], attendance_rate=0.94),
            "NIGHT": ShiftResource(shift_code="NIGHT", team_id="T-B", team_name="乙班", start_at=production_date + "T20:00:00+08:00", end_at=production_date + "T23:59:59+08:00", headcount=15, skill_tags=["组装", "测试", "包装"], attendance_rate=0.88),
        }
        return [shifts[code] for code in shift_codes if code in shifts]

    async def get_work_orders(self, request: SchedulingRequest) -> List[WorkOrder]:
        await self._latency()
        return sorted(request.orders, key=lambda item: (-item.priority, item.due_at, item.order_id))

    async def publish_plan(self, task_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        await self._latency()
        return {"accepted": True, "external_plan_id": "MES-%s" % task_id[-8:], "mode": "mock"}


class HttpWorkshopGateway(WorkshopGateway):
    """真实业务接口实现。端点契约集中在此处，便于对接企业网关。"""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.business_api_base_url:
            raise BusinessGatewayError("真实业务模式需要配置 BUSINESS_API_BASE_URL")
        self.base_url = settings.business_api_base_url.rstrip("/")
        self.timeout = settings.business_api_timeout_seconds
        self.headers = {
            "Authorization": "Bearer %s" % settings.business_api_key,
            "X-Client-System": "forgeflow-agent",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                response = await client.request(method, self.base_url + path, **kwargs)
                response.raise_for_status()
                payload = response.json()
                return payload.get("data", payload)
        except (httpx.HTTPError, ValueError) as exc:
            raise BusinessGatewayError("业务接口 %s 调用失败: %s" % (path, exc)) from exc

    async def get_devices(self, factory_id: str, workshop_id: str) -> List[DeviceResource]:
        data = await self._request("GET", "/v1/equipment/available", params={"factory_id": factory_id, "workshop_id": workshop_id})
        return [DeviceResource.model_validate(item) for item in data]

    async def get_shifts(
        self, factory_id: str, workshop_id: str, production_date: str, shift_codes: List[str]
    ) -> List[ShiftResource]:
        data = await self._request("GET", "/v1/workforce/shifts", params={"factory_id": factory_id, "workshop_id": workshop_id, "date": production_date, "shift_codes": ",".join(shift_codes)})
        return [ShiftResource.model_validate(item) for item in data]

    async def get_work_orders(self, request: SchedulingRequest) -> List[WorkOrder]:
        if request.orders:
            return request.orders
        data = await self._request("GET", "/v1/mes/work-orders", params={"workshop_id": request.workshop_id, "date": request.production_date})
        return [WorkOrder.model_validate(item) for item in data]

    async def publish_plan(self, task_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/v1/mes/schedule-plans", json={"task_id": task_id, "plan": plan})


_gateways: Dict[str, WorkshopGateway] = {"mock": MockWorkshopGateway()}


def get_workshop_gateway(data_source: str) -> WorkshopGateway:
    if data_source == "mock":
        return _gateways["mock"]
    if "real" not in _gateways:
        _gateways["real"] = HttpWorkshopGateway()
    return _gateways["real"]
