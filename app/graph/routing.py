"""Deterministic conditional routing for the V4 assessment graph."""

from app.agents.models import AgentDecisionType
from app.graph.state import AssessmentGraphState


def route_after_reason(state: AssessmentGraphState) -> str:
    """Map the agent's allowlisted decision to one graph node."""
    routes = {
        AgentDecisionType.TOOL: "execute_tool",
        AgentDecisionType.SYNTHESIZE: "synthesize",
        AgentDecisionType.FAIL: "fail",
    }
    return routes[state["next_action"]]
