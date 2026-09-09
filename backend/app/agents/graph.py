"""车间多任务作业规划 LangGraph。"""

from typing import Any, Dict, List, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .nodes.device_resource import device_resource_node
from .nodes.human_review import human_review_node
from .nodes.plan_generate import plan_generate_node
from .nodes.shift_query import shift_query_node
from .nodes.station_assign import station_assign_node


class GraphState(TypedDict):
    task_id: str
    trace_id: str
    request: Dict[str, Any]
    devices: List[Dict[str, Any]]
    shifts: List[Dict[str, Any]]
    work_orders: List[Dict[str, Any]]
    assignments: List[Dict[str, Any]]
    plan: Optional[Dict[str, Any]]
    current_node: str
    status: str
    steps: List[Dict[str, Any]]
    errors: List[str]
    warnings: List[str]
    need_human_review: bool
    human_feedback: Optional[Dict[str, Any]]
    llm_provider: str
    data_source: str
    started_at: str


def should_continue(state: GraphState) -> str:
    return "human_review" if state["request"].get("require_human_review", True) else "end"


def create_scheduling_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("device_resource", device_resource_node)
    workflow.add_node("shift_query", shift_query_node)
    workflow.add_node("station_assign", station_assign_node)
    workflow.add_node("plan_generate", plan_generate_node)
    workflow.add_node("human_review", human_review_node)
    workflow.set_entry_point("device_resource")
    workflow.add_edge("device_resource", "shift_query")
    workflow.add_edge("shift_query", "station_assign")
    workflow.add_edge("station_assign", "plan_generate")
    workflow.add_conditional_edges("plan_generate", should_continue, {"human_review": "human_review", "end": END})
    workflow.add_edge("human_review", END)
    return workflow.compile(checkpointer=MemorySaver())


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = create_scheduling_graph()
    return _graph
