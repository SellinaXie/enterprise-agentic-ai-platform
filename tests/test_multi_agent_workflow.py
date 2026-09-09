"""Deterministic path and native fan-out/fan-in tests for the V5 LangGraph."""

from threading import Barrier
from typing import Any
from uuid import uuid4

import pytest

from app.agents.evidence_agent import EvidenceAgentOutcome
from app.agents.models import AgentTerminationReason
from app.agents.multi_agent_models import EvidenceBrief, MultiAgentStatus
from app.core.exceptions import AssessmentGenerationError
from app.graph.multi_agent_workflow import (
    MultiAgentAssessmentWorkflow,
    build_multi_agent_graph,
)
from app.schemas.assessment import AssessmentRequest
from app.tools.models import ToolHistoryEntry
from tests.factories import (
    build_architecture_recommendation,
    build_assessment_result,
    build_evidence_brief,
    build_risk_governance_review,
)


def _request() -> AssessmentRequest:
    return AssessmentRequest(
        company_name="Example Bank",
        industry="Banking",
        business_problem="Manual compliance review is slow",
        desired_outcome="Reduce preparation time with human approval",
    )


class FakeEvidenceAgent:
    def __init__(
        self,
        brief: EvidenceBrief | None = None,
        *,
        fail: bool = False,
        history: tuple[ToolHistoryEntry, ...] = (),
    ) -> None:
        self.brief = brief or build_evidence_brief()
        self.fail = fail
        self.history = history
        self.calls = 0

    def gather(self, _: AssessmentRequest) -> EvidenceAgentOutcome:
        self.calls += 1
        if self.fail:
            raise RuntimeError("private evidence failure")
        return EvidenceAgentOutcome(
            brief=self.brief,
            evidence=(),
            documents=(),
            tool_history=self.history,
            steps_used=1,
            termination_reason=AgentTerminationReason.AGENT_STOPPED,
        )


class FakeArchitectureAgent:
    def __init__(self, *, fail: bool = False, barrier: Barrier | None = None) -> None:
        self.fail = fail
        self.barrier = barrier
        self.calls: list[tuple[AssessmentRequest, EvidenceBrief]] = []

    def analyze(self, request: AssessmentRequest, brief: EvidenceBrief):  # noqa: ANN201
        self.calls.append((request, brief))
        if self.barrier is not None:
            self.barrier.wait()
        if self.fail:
            raise RuntimeError("private architecture failure")
        return build_architecture_recommendation()


class FakeRiskAgent:
    def __init__(self, *, fail: bool = False, barrier: Barrier | None = None) -> None:
        self.fail = fail
        self.barrier = barrier
        self.calls: list[tuple[AssessmentRequest, EvidenceBrief]] = []

    def review(self, request: AssessmentRequest, brief: EvidenceBrief):  # noqa: ANN201
        self.calls.append((request, brief))
        if self.barrier is not None:
            self.barrier.wait()
        if self.fail:
            raise RuntimeError("private risk failure")
        return build_risk_governance_review()


class FakeSynthesisAgent:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def synthesize(self, **kwargs: Any):  # noqa: ANN201
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("private synthesis failure")
        return build_assessment_result()


def _workflow(
    *,
    evidence: FakeEvidenceAgent | None = None,
    architecture: FakeArchitectureAgent | None = None,
    risk: FakeRiskAgent | None = None,
    synthesis: FakeSynthesisAgent | None = None,
    max_failures: int = 2,
) -> MultiAgentAssessmentWorkflow:
    return MultiAgentAssessmentWorkflow(
        evidence=evidence or FakeEvidenceAgent(),
        architecture=architecture or FakeArchitectureAgent(),
        risk_governance=risk or FakeRiskAgent(),
        synthesis=synthesis or FakeSynthesisAgent(),
        max_failures=max_failures,
    )


def test_path_a_all_specialists_succeed_and_metadata_is_safe() -> None:
    synthesis = FakeSynthesisAgent()

    outcome = _workflow(synthesis=synthesis).run(
        assessment_id=str(uuid4()),
        request=_request(),
    )

    assert outcome.result == build_assessment_result()
    assert outcome.execution.execution_mode == "multi_agent"
    assert outcome.execution.degraded_mode is False
    assert outcome.execution.agent_statuses.model_dump(mode="json") == {
        "evidence": "completed",
        "architecture": "completed",
        "risk_governance": "completed",
        "synthesis": "completed",
    }
    assert [event.sequence for event in outcome.execution.trace] == list(
        range(len(outcome.execution.trace))
    )
    assert "private" not in outcome.execution.model_dump_json()
    assert synthesis.calls[0]["architecture"] == build_architecture_recommendation()
    assert synthesis.calls[0]["risk_governance"] == build_risk_governance_review()


def test_path_b_no_relevant_evidence_is_a_valid_completed_handoff() -> None:
    synthesis = FakeSynthesisAgent()
    evidence = FakeEvidenceAgent(build_evidence_brief())

    outcome = _workflow(evidence=evidence, synthesis=synthesis).run(
        assessment_id=str(uuid4()),
        request=_request(),
    )

    assert outcome.evidence == ()
    assert outcome.execution.agent_statuses.evidence == MultiAgentStatus.COMPLETED
    assert outcome.execution.degraded_mode is False
    assert synthesis.calls[0]["evidence_brief"].retrieved_chunk_ids == []


def test_path_c_architecture_failure_continues_without_fabricating_output() -> None:
    synthesis = FakeSynthesisAgent()

    outcome = _workflow(
        architecture=FakeArchitectureAgent(fail=True),
        synthesis=synthesis,
    ).run(assessment_id=str(uuid4()), request=_request())

    assert outcome.execution.degraded_mode is True
    assert outcome.execution.agent_statuses.architecture == MultiAgentStatus.FAILED
    assert outcome.execution.agent_errors.architecture == "specialist_generation_failed"
    assert synthesis.calls[0]["architecture"] is None
    assert any(
        "Architecture Agent output unavailable" in item for item in outcome.result.information_gaps
    )


def test_path_d_risk_failure_is_explicitly_degraded() -> None:
    synthesis = FakeSynthesisAgent()

    outcome = _workflow(risk=FakeRiskAgent(fail=True), synthesis=synthesis).run(
        assessment_id=str(uuid4()),
        request=_request(),
    )

    assert outcome.execution.degraded_mode is True
    assert outcome.execution.agent_statuses.risk_governance == MultiAgentStatus.FAILED
    assert synthesis.calls[0]["risk_governance"] is None
    assert any("governance confidence reduced" in item for item in outcome.result.information_gaps)


def test_path_e_evidence_failure_uses_explicit_assessment_only_brief() -> None:
    architecture = FakeArchitectureAgent()
    risk = FakeRiskAgent()
    synthesis = FakeSynthesisAgent()

    outcome = _workflow(
        evidence=FakeEvidenceAgent(fail=True),
        architecture=architecture,
        risk=risk,
        synthesis=synthesis,
    ).run(assessment_id=str(uuid4()), request=_request())

    assert outcome.execution.agent_statuses.evidence == MultiAgentStatus.FAILED
    assert outcome.execution.degraded_mode is True
    assert architecture.calls[0][1] == EvidenceBrief.unavailable()
    assert risk.calls[0][1] == EvidenceBrief.unavailable()
    assert synthesis.calls[0]["evidence_brief"] == EvidenceBrief.unavailable()


def test_path_f_synthesis_failure_fails_safely_after_bounded_agent_behavior() -> None:
    with pytest.raises(AssessmentGenerationError):
        _workflow(synthesis=FakeSynthesisAgent(fail=True)).run(
            assessment_id=str(uuid4()),
            request=_request(),
        )


def test_failure_budget_and_minimum_success_policy_prevent_empty_synthesis() -> None:
    synthesis = FakeSynthesisAgent()

    with pytest.raises(AssessmentGenerationError):
        _workflow(
            evidence=FakeEvidenceAgent(fail=True),
            architecture=FakeArchitectureAgent(fail=True),
            risk=FakeRiskAgent(fail=True),
            synthesis=synthesis,
        ).run(assessment_id=str(uuid4()), request=_request())

    assert synthesis.calls == []


def test_unauthorized_tool_observation_becomes_safe_trace_metadata() -> None:
    history = (
        ToolHistoryEntry(
            step=1,
            tool_name="write_database",
            success=False,
            summary="The specialist is not authorized to use the requested tool.",
            argument_keys=("payload",),
            call_fingerprint="safe-fingerprint",
            cached=False,
            error_code="unauthorized_tool",
        ),
    )

    outcome = _workflow(evidence=FakeEvidenceAgent(history=history)).run(
        assessment_id=str(uuid4()),
        request=_request(),
    )

    event = next(
        item for item in outcome.execution.trace if item.event_type == "tool_authorization_denied"
    )
    assert event.tool_name == "write_database"
    assert event.error_code == "unauthorized_tool"
    assert "payload" not in outcome.execution.model_dump_json()


def test_native_parallel_fanout_and_deterministic_fanin_use_both_branch_outputs() -> None:
    barrier = Barrier(2, timeout=3)
    architecture = FakeArchitectureAgent(barrier=barrier)
    risk = FakeRiskAgent(barrier=barrier)
    synthesis = FakeSynthesisAgent()
    graph = build_multi_agent_graph(
        evidence=FakeEvidenceAgent(),
        architecture=architecture,
        risk_governance=risk,
        synthesis=synthesis,
    )
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}

    outcome = _workflow(
        architecture=architecture,
        risk=risk,
        synthesis=synthesis,
    ).run(assessment_id=str(uuid4()), request=_request())

    assert ("evidence", "architecture") in edges
    assert ("evidence", "risk_governance") in edges
    assert ("architecture", "synthesis") in edges
    assert ("risk_governance", "synthesis") in edges
    assert len(synthesis.calls) == 1
    assert synthesis.calls[0]["architecture"] is not None
    assert synthesis.calls[0]["risk_governance"] is not None
    assert outcome.execution.agent_statuses.synthesis == MultiAgentStatus.COMPLETED
