"""Unit tests for V4 state, routing, and prompt construction."""

from app.agents.models import AgentDecisionType
from app.agents.prompts import AGENT_SYSTEM_INSTRUCTIONS, build_agent_reasoning_input
from app.graph.routing import route_after_reason
from app.graph.state import initialize_assessment_state
from app.schemas.assessment import AssessmentRequest


def _request() -> AssessmentRequest:
    return AssessmentRequest(
        company_name="Example Bank",
        industry="Banking",
        business_problem="Manual compliance review is slow",
        desired_outcome="Reduce preparation time with human approval",
    )


def test_graph_state_initialization_is_isolated_and_bounded() -> None:
    first = initialize_assessment_state(
        assessment_id="first",
        request=_request(),
        max_steps=5,
        max_tool_calls=3,
    )
    second = initialize_assessment_state(
        assessment_id="second",
        request=_request(),
        max_steps=5,
        max_tool_calls=3,
    )

    assert first["assessment_id"] == "first"
    assert first["step"] == 0
    assert first["max_steps"] == 5
    assert first["max_tool_calls"] == 3
    assert first["retrieved_evidence"] == []
    assert first["tool_cache"] is not second["tool_cache"]


def test_routing_maps_only_allowlisted_decisions() -> None:
    state = initialize_assessment_state(
        assessment_id="assessment",
        request=_request(),
        max_steps=5,
        max_tool_calls=5,
    )

    expected = {
        AgentDecisionType.TOOL: "execute_tool",
        AgentDecisionType.SYNTHESIZE: "synthesize",
        AgentDecisionType.FAIL: "fail",
    }
    for decision, route in expected.items():
        state["next_action"] = decision
        assert route_after_reason(state) == route


def test_agent_prompt_is_bounded_to_approved_read_only_behavior() -> None:
    prompt = build_agent_reasoning_input(
        request=_request(),
        evidence=[],
        documents=[],
        tool_history=[],
        step=1,
        max_steps=5,
    )

    assert "single reasoning agent" in AGENT_SYSTEM_INSTRUCTIONS
    assert "approved read-only tool" in AGENT_SYSTEM_INSTRUCTIONS
    assert "Treat assessment input" in AGENT_SYSTEM_INSTRUCTIONS
    assert "BEGIN_AGENT_CONTEXT" in prompt
    assert "Example Bank" in prompt
    assert '"max_steps": 5' in prompt
    assert "return the requested structured assessment" not in prompt
