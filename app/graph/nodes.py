"""LangGraph nodes for bounded reason, act, observe, and synthesis behavior."""

import logging
from datetime import UTC, datetime
from typing import Literal

from app.agents.assessment_agent import AssessmentAgent
from app.agents.models import (
    AgentDecisionType,
    AgentTerminationReason,
    AgentTraceEvent,
    AgentTraceEventType,
)
from app.graph.state import AssessmentGraphState
from app.tools.models import ToolHistoryEntry
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _event(
    *,
    step: int,
    event_type: AgentTraceEventType,
    summary: str,
    tool_name: str | None = None,
    tool_status: Literal["completed", "failed", "cached"] | None = None,
    termination_reason: AgentTerminationReason | None = None,
) -> AgentTraceEvent:
    return AgentTraceEvent(
        step=step,
        event_type=event_type,
        timestamp=datetime.now(UTC),
        summary=summary,
        tool_name=tool_name,
        tool_status=tool_status,
        termination_reason=termination_reason,
    )


class AssessmentGraphNodes:
    """Node implementations bound to one agent and one explicit tool registry."""

    def __init__(self, *, agent: AssessmentAgent, tools: ToolRegistry) -> None:
        self._agent = agent
        self._tools = tools

    def reason(self, state: AssessmentGraphState) -> dict[str, object]:
        """Ask the single agent for one action, subject to hard execution limits."""
        log_context = {
            "assessment_id": state["assessment_id"],
            "request_id": state["request_id"],
            "step_count": state["step"],
        }
        logger.info("agent_reason_node_entered", extra=log_context)

        if state["step"] >= state["max_steps"]:
            event = _event(
                step=state["step"],
                event_type=AgentTraceEventType.MAX_STEPS_REACHED,
                summary="The configured reasoning-step limit was reached.",
                termination_reason=AgentTerminationReason.MAX_STEPS_REACHED,
            )
            logger.warning("agent_max_steps_reached", extra=log_context)
            return {
                "next_action": AgentDecisionType.SYNTHESIZE,
                "termination_reason": AgentTerminationReason.MAX_STEPS_REACHED,
                "trace": [*state["trace"], event],
            }

        if state["tool_calls_used"] >= state["max_tool_calls"]:
            event = _event(
                step=state["step"],
                event_type=AgentTraceEventType.MAX_TOOL_CALLS_REACHED,
                summary="The configured tool-call limit was reached.",
                termination_reason=AgentTerminationReason.MAX_TOOL_CALLS_REACHED,
            )
            logger.warning("agent_max_tool_calls_reached", extra=log_context)
            return {
                "next_action": AgentDecisionType.SYNTHESIZE,
                "termination_reason": AgentTerminationReason.MAX_TOOL_CALLS_REACHED,
                "trace": [*state["trace"], event],
            }

        step = state["step"] + 1
        trace = [
            *state["trace"],
            _event(
                step=step,
                event_type=AgentTraceEventType.REASONING_STARTED,
                summary="The agent evaluated whether more approved evidence was needed.",
            ),
        ]
        decision = self._agent.decide(
            request=state["request"],
            evidence=state["retrieved_evidence"],
            documents=state["observed_documents"],
            tool_history=state["tool_history"],
            step=step,
            max_steps=state["max_steps"],
            tool_schemas=self._tools.schemas(),
        )
        updates: dict[str, object] = {
            "step": step,
            "next_action": decision.action,
            "pending_tool_name": None,
            "pending_tool_arguments": {},
            "trace": trace,
        }
        if decision.action == AgentDecisionType.TOOL and decision.tool_request is not None:
            tool_name = decision.tool_request.name
            logger.info(
                "agent_tool_requested",
                extra={**log_context, "step_count": step, "tool_name": tool_name},
            )
            updates.update(
                {
                    "pending_tool_name": tool_name,
                    "pending_tool_arguments": decision.tool_request.arguments,
                    "trace": [
                        *trace,
                        _event(
                            step=step,
                            event_type=AgentTraceEventType.TOOL_REQUESTED,
                            summary="The agent requested one approved read-only tool.",
                            tool_name=tool_name,
                        ),
                    ],
                }
            )
        elif decision.action == AgentDecisionType.SYNTHESIZE:
            updates["termination_reason"] = AgentTerminationReason.AGENT_STOPPED
        elif decision.action == AgentDecisionType.FAIL:
            updates["termination_reason"] = AgentTerminationReason.FAILED
        return updates

    def execute_tool(self, state: AssessmentGraphState) -> dict[str, object]:
        """Validate and execute one allowlisted tool, then record its observation."""
        tool_name = state["pending_tool_name"] or ""
        cache = dict(state["tool_cache"])
        result, fingerprint, argument_keys = self._tools.execute(
            tool_name,
            state["pending_tool_arguments"],
            cache=cache,
        )
        history = [
            *state["tool_history"],
            ToolHistoryEntry(
                step=state["step"],
                tool_name=tool_name,
                success=result.success,
                summary=result.summary,
                argument_keys=argument_keys,
                call_fingerprint=fingerprint,
                cached=result.cached,
                error_code=result.error_code,
            ),
        ]
        log_context = {
            "assessment_id": state["assessment_id"],
            "request_id": state["request_id"],
            "step_count": state["step"],
            "tool_name": tool_name,
        }

        evidence_by_chunk = {item.chunk_id: item for item in state["retrieved_evidence"]}
        for item in result.evidence:
            evidence_by_chunk.setdefault(item.chunk_id, item)
        documents_by_id = {item.document_id: item for item in state["observed_documents"]}
        if result.document is not None:
            documents_by_id.setdefault(result.document.document_id, result.document)

        event_type = (
            AgentTraceEventType.TOOL_COMPLETED
            if result.success
            else AgentTraceEventType.TOOL_FAILED
        )
        tool_status: Literal["completed", "failed", "cached"] = (
            "cached" if result.cached else "completed" if result.success else "failed"
        )
        log_event = "agent_tool_completed" if result.success else "agent_tool_failed"
        log_method = logger.info if result.success else logger.warning
        log_method(log_event, extra={**log_context, "tool_status": tool_status})
        return {
            "retrieved_evidence": list(evidence_by_chunk.values()),
            "observed_documents": list(documents_by_id.values()),
            "tool_history": history,
            "tool_cache": cache,
            "tool_calls_used": state["tool_calls_used"] + 1,
            "pending_tool_name": None,
            "pending_tool_arguments": {},
            "trace": [
                *state["trace"],
                _event(
                    step=state["step"],
                    event_type=event_type,
                    summary=result.summary,
                    tool_name=tool_name,
                    tool_status=tool_status,
                ),
            ],
        }

    def synthesize(self, state: AssessmentGraphState) -> dict[str, object]:
        """Generate the existing structured assessment from observed evidence."""
        termination_reason = state["termination_reason"] or AgentTerminationReason.COMPLETED
        log_context = {
            "assessment_id": state["assessment_id"],
            "request_id": state["request_id"],
            "step_count": state["step"],
        }
        logger.info("agent_synthesis_started", extra=log_context)
        started = _event(
            step=state["step"],
            event_type=AgentTraceEventType.SYNTHESIS_STARTED,
            summary="Schema-constrained assessment synthesis started.",
        )
        result = self._agent.synthesize(
            request=state["request"],
            evidence=state["retrieved_evidence"],
            documents=state["observed_documents"],
        )
        completed = _event(
            step=state["step"],
            event_type=AgentTraceEventType.WORKFLOW_COMPLETED,
            summary="The agentic workflow produced a structured assessment.",
            termination_reason=termination_reason,
        )
        logger.info(
            "agent_workflow_completed",
            extra={**log_context, "termination_reason": termination_reason.value},
        )
        return {
            "final_result": result,
            "termination_reason": termination_reason,
            "trace": [*state["trace"], started, completed],
        }

    def fail(self, state: AssessmentGraphState) -> dict[str, object]:
        """Terminate explicitly without exposing the agent's private provider output."""
        logger.warning(
            "agent_workflow_failed",
            extra={
                "assessment_id": state["assessment_id"],
                "request_id": state["request_id"],
                "step_count": state["step"],
            },
        )
        return {
            "error": "agent_terminated_without_result",
            "termination_reason": AgentTerminationReason.FAILED,
            "trace": [
                *state["trace"],
                _event(
                    step=state["step"],
                    event_type=AgentTraceEventType.WORKFLOW_FAILED,
                    summary="The agentic workflow terminated without a final result.",
                    termination_reason=AgentTerminationReason.FAILED,
                ),
            ],
        }
