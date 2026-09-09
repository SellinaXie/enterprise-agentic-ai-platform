"""Typed decisions and safe execution metadata for the V4 assessment agent."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentDecisionType(StrEnum):
    """Allowlisted transitions that the single reasoning agent may request."""

    TOOL = "tool"
    SYNTHESIZE = "synthesize"
    FAIL = "fail"


class AgentTraceEventType(StrEnum):
    """Safe workflow events that intentionally omit private reasoning."""

    REASONING_STARTED = "reasoning_started"
    TOOL_REQUESTED = "tool_requested"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    SYNTHESIS_STARTED = "synthesis_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    MAX_STEPS_REACHED = "max_steps_reached"
    MAX_TOOL_CALLS_REACHED = "max_tool_calls_reached"


class AgentTerminationReason(StrEnum):
    """Finite, public-safe workflow termination reasons."""

    COMPLETED = "completed"
    MAX_STEPS_REACHED = "max_steps_reached"
    MAX_TOOL_CALLS_REACHED = "max_tool_calls_reached"
    AGENT_STOPPED = "agent_stopped"
    FAILED = "failed"


class AgentToolRequest(BaseModel):
    """Provider-neutral function request selected by the reasoning agent."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any]


class AgentDecision(BaseModel):
    """One bounded routing decision without a chain-of-thought field."""

    model_config = ConfigDict(extra="forbid")

    action: AgentDecisionType
    tool_request: AgentToolRequest | None = None

    @model_validator(mode="after")
    def validate_tool_request(self) -> "AgentDecision":
        if self.action == AgentDecisionType.TOOL and self.tool_request is None:
            raise ValueError("Tool decisions require one tool request")
        if self.action != AgentDecisionType.TOOL and self.tool_request is not None:
            raise ValueError("Only tool decisions may include a tool request")
        return self


class AgentTraceEvent(BaseModel):
    """Compact audit event containing decisions and outcomes, not hidden reasoning."""

    model_config = ConfigDict(extra="forbid")

    step: int = Field(ge=0)
    event_type: AgentTraceEventType
    timestamp: datetime
    summary: str = Field(min_length=1, max_length=300)
    tool_name: str | None = Field(default=None, max_length=100)
    tool_status: Literal["completed", "failed", "cached"] | None = None
    termination_reason: AgentTerminationReason | None = None


class AssessmentExecutionMetadata(BaseModel):
    """Safe execution summary persisted with an agentic assessment."""

    model_config = ConfigDict(extra="forbid")

    execution_mode: Literal["agentic"] = "agentic"
    steps_used: int = Field(ge=0)
    tools_used: list[str]
    termination_reason: AgentTerminationReason
    trace: list[AgentTraceEvent]
