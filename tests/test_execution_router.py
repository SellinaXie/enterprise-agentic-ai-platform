"""Focused contracts for deterministic per-request execution routing."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.agents.models import (
    AgentTerminationReason,
    AssessmentExecutionMetadata,
)
from app.agents.multi_agent_models import (
    MultiAgentDurations,
    MultiAgentErrors,
    MultiAgentExecutionMetadata,
    MultiAgentStatus,
    MultiAgentStatuses,
    MultiAgentTerminationReason,
)
from app.api.dependencies import (
    get_agentic_assessment_workflow,
    get_execution_router,
    get_multi_agent_assessment_workflow,
)
from app.core.config import Settings
from app.models.assessment import AssessmentStatus
from app.repositories.assessments import AssessmentRepository
from app.repositories.runtime_reviews import RuntimeReviewRepository
from app.runtime.gate import RuntimeRiskGate
from app.runtime.models import HumanReviewRequest, RuntimeRiskDecision, RuntimeRiskPolicy
from app.schemas.assessment import AssessmentRequest
from app.services.assessments import AssessmentGenerator, AssessmentService
from app.services.execution_router import (
    ExecutionMode,
    ExecutionRouter,
    FallbackReasonCode,
    RoutingReasonCode,
)
from app.services.runtime_governance import RuntimeGovernanceService
from tests.factories import build_assessment_result


def _request(**updates: object) -> AssessmentRequest:
    values: dict[str, object] = {
        "company_name": "Example Company",
        "industry": "Shared Industry",
        "business_problem": "Rename incoming files using a fixed lookup table",
        "desired_outcome": "Produce validated file names",
    }
    values.update(updates)
    return AssessmentRequest.model_validate(values)


def _moderate_request() -> AssessmentRequest:
    return _request(
        business_problem="Reduce manual document review and inconsistent handoffs",
        current_process="One operations team reviews each document in a shared system.",
        pain_points=["Repeated data entry", "Inconsistent review summaries"],
        constraints=["Preserve human approval", "Use existing access controls"],
        desired_outcome="Assist reviewers with a traceable recommendation",
    )


def _complex_request() -> AssessmentRequest:
    return _request(
        business_problem=(
            "Coordinate a cross-functional decision across systems while protecting customer data"
        ),
        current_process=(
            "Multiple teams perform security, compliance, operations, and integration reviews."
        ),
        pain_points=[
            "Security findings are reviewed separately",
            "Audit evidence is fragmented",
            "Operations monitoring is inconsistent",
        ],
        constraints=[
            "Preserve privacy controls",
            "Retain human approval",
            "Integrate with existing APIs",
        ],
        desired_outcome="Synthesize specialist perspectives into one governed recommendation",
        additional_context="The process has multiple stakeholders and parallel workstreams.",
    )


def _multi_execution() -> MultiAgentExecutionMetadata:
    return MultiAgentExecutionMetadata(
        agent_statuses=MultiAgentStatuses(
            evidence=MultiAgentStatus.COMPLETED,
            architecture=MultiAgentStatus.COMPLETED,
            risk_governance=MultiAgentStatus.COMPLETED,
            synthesis=MultiAgentStatus.COMPLETED,
        ),
        agent_durations_ms=MultiAgentDurations(
            evidence=1,
            architecture=1,
            risk_governance=1,
            synthesis=1,
        ),
        agent_errors=MultiAgentErrors(),
        tools_used=[],
        tool_calls=0,
        degraded_mode=False,
        degradation_reasons=[],
        termination_reason=MultiAgentTerminationReason.COMPLETED,
        trace=[],
    )


def _service(
    db_session: Session,
    *,
    router: ExecutionRouter,
    single_agent_available: bool = True,
    multi_agent_available: bool = True,
) -> tuple[
    AssessmentService,
    RuntimeGovernanceService,
    AssessmentRepository,
    Mock,
    Mock,
    Mock,
]:
    result = build_assessment_result()
    generator = Mock()
    generator.generate.return_value = result
    single_workflow = Mock()
    single_workflow.run.return_value = SimpleNamespace(
        result=result,
        evidence=(),
        execution=AssessmentExecutionMetadata(
            steps_used=1,
            tools_used=[],
            termination_reason=AgentTerminationReason.COMPLETED,
            trace=[],
        ),
    )
    multi_workflow = Mock()
    multi_workflow.run.return_value = SimpleNamespace(
        result=result,
        evidence=(),
        execution=_multi_execution(),
    )
    assessments = AssessmentRepository(db_session)
    runtime = RuntimeGovernanceService(
        assessments=assessments,
        reviews=RuntimeReviewRepository(db_session),
        gate=RuntimeRiskGate(RuntimeRiskPolicy()),
    )
    service = AssessmentService(
        cast(AssessmentGenerator, generator),
        assessments,
        agentic_workflow=single_workflow if single_agent_available else None,
        multi_agent_workflow=multi_workflow if multi_agent_available else None,
        runtime_governance=runtime,
        execution_router=router,
    )
    return service, runtime, assessments, generator, single_workflow, multi_workflow


def test_simple_bounded_request_routes_deterministic() -> None:
    decision = ExecutionRouter().route(_request())

    assert decision.preferred_execution_mode == ExecutionMode.DETERMINISTIC
    assert decision.reason_codes == [
        RoutingReasonCode.BOUNDED_SCOPE,
        RoutingReasonCode.LOW_COORDINATION_COMPLEXITY,
    ]


def test_moderately_complex_request_routes_single_agent() -> None:
    decision = ExecutionRouter().route(_moderate_request())

    assert decision.preferred_execution_mode == ExecutionMode.SINGLE_AGENT
    assert RoutingReasonCode.MULTIPLE_PAIN_POINTS in decision.reason_codes
    assert RoutingReasonCode.MULTIPLE_CONSTRAINTS in decision.reason_codes
    assert RoutingReasonCode.SINGLE_REASONING_CONTEXT_SUFFICIENT in decision.reason_codes


def test_cross_functional_complex_request_routes_multi_agent() -> None:
    decision = ExecutionRouter().route(_complex_request())

    assert decision.preferred_execution_mode == ExecutionMode.MULTI_AGENT
    assert RoutingReasonCode.CROSS_FUNCTIONAL_COORDINATION in decision.reason_codes
    assert RoutingReasonCode.SPECIALIST_SEPARATION_BENEFICIAL in decision.reason_codes


def test_same_industry_routes_differently_by_workload_complexity() -> None:
    simple = ExecutionRouter().route(_request(industry="Identical Industry"))
    complex_decision = ExecutionRouter().route(
        _complex_request().model_copy(update={"industry": "Identical Industry"})
    )

    assert simple.preferred_execution_mode == ExecutionMode.DETERMINISTIC
    assert complex_decision.preferred_execution_mode == ExecutionMode.MULTI_AGENT


def test_execution_mode_override_is_the_only_forced_route(db_session: Session) -> None:
    settings = Settings(
        _env_file=None,
        EXECUTION_MODE_OVERRIDE="multi_agent",
        AGENTIC_WORKFLOW_ENABLED=False,
        MULTI_AGENT_WORKFLOW_ENABLED=False,
    )
    router = get_execution_router(settings)

    assert router is not None
    decision = router.route(_request())
    assert decision.preferred_execution_mode == ExecutionMode.MULTI_AGENT
    assert decision.reason_codes == [RoutingReasonCode.ENVIRONMENT_OVERRIDE]
    assert (
        get_multi_agent_assessment_workflow(
            evidence=Mock(),
            architecture=Mock(),
            risk_governance=Mock(),
            synthesis=Mock(),
            settings=settings,
        )
        is not None
    )
    service, _, _, _, _, multi_workflow = _service(
        db_session,
        router=router,
        single_agent_available=False,
        multi_agent_available=True,
    )
    response = service.generate_assessment(_request())
    assert response.execution is not None
    assert response.execution.preferred_execution_mode == ExecutionMode.MULTI_AGENT.value
    assert response.execution.execution_mode == ExecutionMode.MULTI_AGENT.value
    multi_workflow.run.assert_called_once()


def test_capability_flags_do_not_force_the_router() -> None:
    router = get_execution_router(
        Settings(
            _env_file=None,
            EXECUTION_ROUTING_ENABLED=True,
            AGENTIC_WORKFLOW_ENABLED=True,
            MULTI_AGENT_WORKFLOW_ENABLED=True,
        )
    )

    assert router is not None
    assert router.route(_request()).preferred_execution_mode == ExecutionMode.DETERMINISTIC


@pytest.mark.parametrize(
    ("workload_request", "mode"),
    [
        (_request(), ExecutionMode.DETERMINISTIC),
        (_moderate_request(), ExecutionMode.SINGLE_AGENT),
        (_complex_request(), ExecutionMode.MULTI_AGENT),
    ],
    ids=["deterministic", "single-agent", "multi-agent"],
)
def test_preferred_and_actual_mode_persist_while_risk_gate_remains_independent(
    db_session: Session,
    workload_request: AssessmentRequest,
    mode: ExecutionMode,
) -> None:
    service, runtime, assessments, generator, single_workflow, multi_workflow = _service(
        db_session,
        router=ExecutionRouter(),
    )

    response = service.generate_assessment(workload_request)

    assert response.status == AssessmentStatus.PENDING_REVIEW
    assert response.execution is not None
    assert response.execution.execution_mode == mode.value
    assert response.execution.preferred_execution_mode == mode.value
    assert response.execution.routing_reason_codes
    assert response.execution.fallback_reason_codes == []
    persisted = assessments.get_by_id(response.assessment_id)
    assert persisted is not None
    assert persisted.execution_metadata is not None
    assert persisted.execution_metadata["execution_mode"] == mode.value
    assert persisted.execution_metadata["preferred_execution_mode"] == mode.value
    assert persisted.execution_metadata["routing_reason_codes"]
    assert persisted.execution_metadata["fallback_reason_codes"] == []
    runtime_status = runtime.get_runtime_status(response.assessment_id)
    assert runtime_status.gate_result.decision == RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW
    assert runtime_status.telemetry.execution_mode == mode.value

    approved = runtime.approve(
        response.assessment_id,
        HumanReviewRequest(reviewer_id="synthetic-reviewer", comment="Approved."),
    )
    assert approved.assessment_status == AssessmentStatus.COMPLETED.value

    if mode == ExecutionMode.DETERMINISTIC:
        generator.generate.assert_called_once()
        single_workflow.run.assert_not_called()
        multi_workflow.run.assert_not_called()
    elif mode == ExecutionMode.SINGLE_AGENT:
        generator.generate.assert_not_called()
        single_workflow.run.assert_called_once()
        multi_workflow.run.assert_not_called()
    else:
        generator.generate.assert_not_called()
        single_workflow.run.assert_not_called()
        multi_workflow.run.assert_called_once()


@pytest.mark.parametrize(
    ("single_agent_available", "expected_mode", "expected_fallbacks"),
    [
        (
            True,
            ExecutionMode.SINGLE_AGENT,
            [
                FallbackReasonCode.MULTI_AGENT_CAPABILITY_UNAVAILABLE.value,
                FallbackReasonCode.FALLBACK_TO_SINGLE_AGENT.value,
            ],
        ),
        (
            False,
            ExecutionMode.DETERMINISTIC,
            [
                FallbackReasonCode.MULTI_AGENT_CAPABILITY_UNAVAILABLE.value,
                FallbackReasonCode.SINGLE_AGENT_CAPABILITY_UNAVAILABLE.value,
                FallbackReasonCode.FALLBACK_TO_DETERMINISTIC.value,
            ],
        ),
    ],
    ids=["single-agent-fallback", "deterministic-fallback"],
)
def test_multi_agent_preference_falls_back_by_capability(
    db_session: Session,
    single_agent_available: bool,
    expected_mode: ExecutionMode,
    expected_fallbacks: list[str],
) -> None:
    service, _, assessments, generator, single_workflow, multi_workflow = _service(
        db_session,
        router=ExecutionRouter(),
        single_agent_available=single_agent_available,
        multi_agent_available=False,
    )

    response = service.generate_assessment(_complex_request())

    assert response.execution is not None
    assert response.execution.preferred_execution_mode == ExecutionMode.MULTI_AGENT.value
    assert response.execution.execution_mode == expected_mode.value
    assert response.execution.fallback_reason_codes == expected_fallbacks
    persisted = assessments.get_by_id(response.assessment_id)
    assert persisted is not None and persisted.execution_metadata is not None
    assert persisted.execution_metadata["preferred_execution_mode"] == "multi_agent"
    assert persisted.execution_metadata["execution_mode"] == expected_mode.value
    assert persisted.execution_metadata["fallback_reason_codes"] == expected_fallbacks
    multi_workflow.run.assert_not_called()
    if single_agent_available:
        single_workflow.run.assert_called_once()
        generator.generate.assert_not_called()
    else:
        single_workflow.run.assert_not_called()
        generator.generate.assert_called_once()


@pytest.mark.parametrize(
    ("agentic_enabled", "multi_agent_enabled", "has_single_agent", "has_multi_agent"),
    [
        (False, False, False, False),
        (True, False, True, False),
        (False, True, False, True),
        (True, True, False, True),
    ],
    ids=["deterministic", "single-agent", "multi-agent", "multi-agent-precedence"],
)
def test_routing_disabled_preserves_legacy_flag_behavior(
    agentic_enabled: bool,
    multi_agent_enabled: bool,
    has_single_agent: bool,
    has_multi_agent: bool,
) -> None:
    settings = Settings(
        _env_file=None,
        EXECUTION_ROUTING_ENABLED=False,
        AGENTIC_WORKFLOW_ENABLED=agentic_enabled,
        MULTI_AGENT_WORKFLOW_ENABLED=multi_agent_enabled,
    )

    assert get_execution_router(settings) is None
    single = get_agentic_assessment_workflow(agent=Mock(), tools=Mock(), settings=settings)
    multi = get_multi_agent_assessment_workflow(
        evidence=Mock(),
        architecture=Mock(),
        risk_governance=Mock(),
        synthesis=Mock(),
        settings=settings,
    )
    assert (single is not None) is has_single_agent
    assert (multi is not None) is has_multi_agent
