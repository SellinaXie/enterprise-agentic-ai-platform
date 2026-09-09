"""Controlled four-agent LangGraph workflow for V5 assessments."""

from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.architecture_agent import ArchitectureAgent
from app.agents.evidence_agent import EvidenceAgent
from app.agents.multi_agent_models import MultiAgentExecutionMetadata
from app.agents.risk_governance_agent import RiskGovernanceAgent
from app.agents.synthesis_agent import SynthesisAgent
from app.core.exceptions import ApplicationError, AssessmentGenerationError
from app.graph.multi_agent_nodes import MultiAgentGraphNodes
from app.graph.multi_agent_state import MultiAgentGraphState, initialize_multi_agent_state
from app.models.knowledge import RetrievedEvidence
from app.schemas.assessment import AssessmentRequest, AssessmentResult


@dataclass(frozen=True, slots=True)
class MultiAgentWorkflowResult:
    """Compatible result, observed evidence, and safe V5 execution metadata."""

    result: AssessmentResult
    evidence: tuple[RetrievedEvidence, ...]
    execution: MultiAgentExecutionMetadata


def build_multi_agent_graph(
    *,
    evidence: EvidenceAgent,
    architecture: ArchitectureAgent,
    risk_governance: RiskGovernanceAgent,
    synthesis: SynthesisAgent,
) -> CompiledStateGraph:
    """Compile true fan-out/fan-in orchestration with an explicit validation node."""
    nodes = MultiAgentGraphNodes(
        evidence=evidence,
        architecture=architecture,
        risk_governance=risk_governance,
        synthesis=synthesis,
    )
    graph = StateGraph(MultiAgentGraphState)
    graph.add_node("initialize", nodes.initialize)
    graph.add_node("evidence", nodes.evidence)
    graph.add_node("architecture", nodes.architecture)
    graph.add_node("risk_governance", nodes.risk_governance)
    graph.add_node("synthesis", nodes.synthesize)
    graph.add_node("validate", nodes.validate)
    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "evidence")
    graph.add_edge("evidence", "architecture")
    graph.add_edge("evidence", "risk_governance")
    graph.add_edge(["architecture", "risk_governance"], "synthesis")
    graph.add_edge("synthesis", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


class MultiAgentAssessmentWorkflow:
    """Invoke one isolated V5 graph subject to the configured partial-failure policy."""

    def __init__(
        self,
        *,
        evidence: EvidenceAgent,
        architecture: ArchitectureAgent,
        risk_governance: RiskGovernanceAgent,
        synthesis: SynthesisAgent,
        max_failures: int,
    ) -> None:
        self._graph = build_multi_agent_graph(
            evidence=evidence,
            architecture=architecture,
            risk_governance=risk_governance,
            synthesis=synthesis,
        )
        self._max_failures = max_failures

    def run(
        self,
        *,
        assessment_id: str,
        request: AssessmentRequest,
    ) -> MultiAgentWorkflowResult:
        """Run the graph and require successful schema-constrained synthesis."""
        try:
            state = self._graph.invoke(
                initialize_multi_agent_state(
                    assessment_id=assessment_id,
                    request=request,
                    max_failures=self._max_failures,
                )
            )
        except ApplicationError:
            raise
        except Exception as exc:
            raise AssessmentGenerationError from exc
        result = state.get("final_result")
        execution = state.get("execution")
        if result is None or execution is None:
            raise AssessmentGenerationError
        return MultiAgentWorkflowResult(
            result=AssessmentResult.model_validate(result),
            evidence=tuple(state["retrieved_evidence"]),
            execution=MultiAgentExecutionMetadata.model_validate(execution),
        )
