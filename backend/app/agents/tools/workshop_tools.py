"""面向 Agent 的四个业务工具。

节点使用同一 Toolset 的类型化方法；`as_langchain_tools` 可直接用于后续 ReAct 场景。
"""

import json
from typing import Any, Dict, List

from langchain_core.tools import StructuredTool

from ...models.schemas import SchedulingRequest
from ...services.business_gateway import get_workshop_gateway


class WorkshopToolset:
    def __init__(self, data_source: str):
        self.data_source = data_source
        self.gateway = get_workshop_gateway(data_source)

    async def query_available_devices(self, factory_id: str, workshop_id: str) -> List[Dict[str, Any]]:
        records = await self.gateway.get_devices(factory_id, workshop_id)
        return [record.model_dump(mode="json") for record in records]

    async def query_shift_roster(
        self, factory_id: str, workshop_id: str, production_date: str, shift_codes: List[str]
    ) -> List[Dict[str, Any]]:
        records = await self.gateway.get_shifts(factory_id, workshop_id, production_date, shift_codes)
        return [record.model_dump(mode="json") for record in records]

    async def query_work_orders(self, request: SchedulingRequest) -> List[Dict[str, Any]]:
        records = await self.gateway.get_work_orders(request)
        return [record.model_dump(mode="json") for record in records]

    async def publish_approved_plan(self, task_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        return await self.gateway.publish_plan(task_id, plan)

    def as_langchain_tools(self) -> List[StructuredTool]:
        async def devices(factory_id: str, workshop_id: str) -> str:
            return json.dumps(await self.query_available_devices(factory_id, workshop_id), ensure_ascii=False)

        async def shifts(factory_id: str, workshop_id: str, production_date: str, shift_codes: List[str]) -> str:
            return json.dumps(await self.query_shift_roster(factory_id, workshop_id, production_date, shift_codes), ensure_ascii=False)

        async def orders(request_json: str) -> str:
            request = SchedulingRequest.model_validate_json(request_json)
            return json.dumps(await self.query_work_orders(request), ensure_ascii=False)

        async def publish(task_id: str, plan_json: str) -> str:
            return json.dumps(await self.publish_approved_plan(task_id, json.loads(plan_json)), ensure_ascii=False)

        return [
            StructuredTool.from_function(coroutine=devices, name="query_available_devices", description="查询车间可用设备、工位能力与 OEE"),
            StructuredTool.from_function(coroutine=shifts, name="query_shift_roster", description="查询指定生产日的班组排班与技能"),
            StructuredTool.from_function(coroutine=orders, name="query_work_orders", description="查询并按优先级整理 MES 工单"),
            StructuredTool.from_function(coroutine=publish, name="publish_approved_plan", description="将审核通过的计划下发至 MES"),
        ]


def get_toolset(data_source: str) -> WorkshopToolset:
    return WorkshopToolset(data_source)

