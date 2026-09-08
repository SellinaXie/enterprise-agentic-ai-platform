"""Minimal LangGraph scaffold for future assessment orchestration."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


class AssessmentGraphState(TypedDict, total=False):
    """Shared state contract for a future assessment workflow."""

    assessment_id: str
    company_name: str
    business_problem: str


def build_assessment_graph() -> CompiledStateGraph:
    """Compile the empty V0 workflow without invoking it from the API."""
    workflow = StateGraph(AssessmentGraphState)
    workflow.add_edge(START, END)
    return workflow.compile()
