"""Provider-neutral typed state for one V4 LangGraph execution."""

from typing import TypedDict

from app.agents.models import AgentDecisionType, AgentTerminationReason, AgentTraceEvent
from app.models.knowledge import RetrievedEvidence
from app.schemas.assessment import AssessmentRequest, AssessmentResult
from app.tools.models import (
    ObservedKnowledgeDocument,
    ToolExecutionResult,
    ToolHistoryEntry,
)


class AssessmentGraphState(TypedDict):
    """Complete application state shared by the graph nodes."""

    assessment_id: str
    request_id: str
    request: AssessmentRequest
    retrieved_evidence: list[RetrievedEvidence]
    observed_documents: list[ObservedKnowledgeDocument]
    tool_history: list[ToolHistoryEntry]
    tool_cache: dict[str, ToolExecutionResult]
    pending_tool_name: str | None
    pending_tool_arguments: dict[str, object]
    next_action: AgentDecisionType
    step: int
    max_steps: int
    tool_calls_used: int
    max_tool_calls: int
    final_result: AssessmentResult | None
    termination_reason: AgentTerminationReason | None
    error: str | None
    trace: list[AgentTraceEvent]


def initialize_assessment_state(
    *,
    assessment_id: str,
    request: AssessmentRequest,
    max_steps: int,
    max_tool_calls: int,
) -> AssessmentGraphState:
    """Create isolated graph state with finite execution guards."""
    if max_steps < 1 or max_tool_calls < 1:
        raise ValueError("Agent step and tool-call limits must be positive")
    return AssessmentGraphState(
        assessment_id=assessment_id,
        request_id=assessment_id,
        request=request,
        retrieved_evidence=[],
        observed_documents=[],
        tool_history=[],
        tool_cache={},
        pending_tool_name=None,
        pending_tool_arguments={},
        next_action=AgentDecisionType.SYNTHESIZE,
        step=0,
        max_steps=max_steps,
        tool_calls_used=0,
        max_tool_calls=max_tool_calls,
        final_result=None,
        termination_reason=None,
        error=None,
        trace=[],
    )
