"""Active, bounded LangGraph workflow for V4 agentic assessments."""

import logging
from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.assessment_agent import AssessmentAgent
from app.agents.models import AssessmentExecutionMetadata
from app.core.exceptions import AssessmentGenerationError
from app.graph.nodes import AssessmentGraphNodes
from app.graph.routing import route_after_reason
from app.graph.state import AssessmentGraphState, initialize_assessment_state
from app.models.knowledge import RetrievedEvidence
from app.schemas.assessment import AssessmentRequest, AssessmentResult
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentWorkflowResult:
    """Validated result, observed evidence, and safe execution metadata."""

    result: AssessmentResult
    evidence: tuple[RetrievedEvidence, ...]
    execution: AssessmentExecutionMetadata


def build_assessment_graph(
    *,
    agent: AssessmentAgent,
    tools: ToolRegistry,
) -> CompiledStateGraph:
    """Compile the executable reason/tool/synthesis graph."""
    nodes = AssessmentGraphNodes(agent=agent, tools=tools)
    graph = StateGraph(AssessmentGraphState)
    graph.add_node("reason", nodes.reason)
    graph.add_node("execute_tool", nodes.execute_tool)
    graph.add_node("synthesize", nodes.synthesize)
    graph.add_node("fail", nodes.fail)
    graph.add_edge(START, "reason")
    graph.add_conditional_edges(
        "reason",
        route_after_reason,
        {
            "execute_tool": "execute_tool",
            "synthesize": "synthesize",
            "fail": "fail",
        },
    )
    graph.add_edge("execute_tool", "reason")
    graph.add_edge("synthesize", END)
    graph.add_edge("fail", END)
    return graph.compile()


class AgenticAssessmentWorkflow:
    """Invoke one compiled graph with explicit application-level limits."""

    def __init__(
        self,
        *,
        agent: AssessmentAgent,
        tools: ToolRegistry,
        max_steps: int,
        max_tool_calls: int,
        recursion_limit: int,
    ) -> None:
        self._graph = build_assessment_graph(agent=agent, tools=tools)
        self._max_steps = max_steps
        self._max_tool_calls = max_tool_calls
        self._recursion_limit = recursion_limit

    def run(
        self,
        *,
        assessment_id: str,
        request: AssessmentRequest,
    ) -> AgentWorkflowResult:
        """Run one isolated workflow and require a schema-valid final result."""
        logger.info(
            "agent_workflow_started",
            extra={"assessment_id": assessment_id, "request_id": assessment_id, "step_count": 0},
        )
        initial_state = initialize_assessment_state(
            assessment_id=assessment_id,
            request=request,
            max_steps=self._max_steps,
            max_tool_calls=self._max_tool_calls,
        )
        try:
            state = self._graph.invoke(
                initial_state,
                config={"recursion_limit": self._recursion_limit},
            )
        except Exception:
            logger.exception(
                "agent_workflow_failed",
                extra={"assessment_id": assessment_id, "request_id": assessment_id},
            )
            raise

        result = state.get("final_result")
        termination_reason = state.get("termination_reason")
        if result is None or termination_reason is None or state.get("error") is not None:
            raise AssessmentGenerationError

        tools_used = list(dict.fromkeys(item.tool_name for item in state["tool_history"]))
        execution = AssessmentExecutionMetadata(
            steps_used=state["step"],
            tools_used=tools_used,
            termination_reason=termination_reason,
            trace=state["trace"],
        )
        return AgentWorkflowResult(
            result=AssessmentResult.model_validate(result),
            evidence=tuple(state["retrieved_evidence"]),
            execution=execution,
        )
