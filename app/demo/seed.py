"""Seed two synthetic assessments that demonstrate opposite runtime-gate outcomes."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.agents.models import DeterministicExecutionMetadata
from app.models.assessment import AssessmentStatus, RiskSeverity
from app.repositories.assessments import AssessmentRepository
from app.repositories.runtime_reviews import RuntimeReviewRepository
from app.runtime.gate import RuntimeRiskGate
from app.runtime.models import RuntimeRiskPolicy
from app.schemas.assessment import AssessmentRequest, AssessmentResult
from app.services.runtime_governance import RuntimeGovernanceService


@dataclass(frozen=True, slots=True)
class SeededDemoAssessment:
    scenario: str
    assessment_id: UUID
    status: AssessmentStatus


def _result(*, high_risk: bool) -> AssessmentResult:
    return AssessmentResult.model_validate(
        {
            "executive_summary": (
                "Use a governed drafting assistant with mandatory review for customer-facing PII."
                if high_risk
                else "Use a bounded internal assistant for low-impact procedure discovery."
            ),
            "problem_analysis": {
                "core_problem": "Employees spend time finding and organizing approved guidance.",
                "current_process_weaknesses": ["Information retrieval is manual."],
                "key_bottlenecks": ["Policy discovery"],
            },
            "ai_suitability": {
                "level": "high",
                "rationale": "Retrieval-assisted drafting can reduce repetitive knowledge work.",
            },
            "recommended_use_cases": [
                {
                    "name": "Governed guidance assistant",
                    "description": "Retrieve approved guidance and prepare a bounded draft.",
                    "expected_business_value": "Reduce preparation time while preserving controls.",
                    "complexity": "medium" if high_risk else "low",
                    "priority": "high",
                }
            ],
            "recommended_solution": {
                "pattern": "rag_decision_support",
                "description": "Use retrieval with citations, validation, and least privilege.",
                "rationale": "The task depends on governed enterprise knowledge.",
            },
            "risks": [
                {
                    "category": "privacy" if high_risk else "operational",
                    "description": (
                        "Customer PII could appear in an inaccurate external response."
                        if high_risk
                        else "An internal answer could be incomplete."
                    ),
                    "severity": RiskSeverity.HIGH if high_risk else RiskSeverity.LOW,
                    "mitigation": (
                        "Minimize data and require an authenticated reviewer before release."
                        if high_risk
                        else "Show citations and provide a clear escalation path."
                    ),
                }
            ],
            "human_oversight": {
                "review_recommended": high_risk,
                "decisions_requiring_review": (
                    ["Any customer-facing response containing personal data"] if high_risk else []
                ),
                "rationale": (
                    "Customer-facing PII creates material privacy and accuracy risk."
                    if high_risk
                    else "The assistant is informational and does not execute decisions."
                ),
            },
            "next_steps": [
                {
                    "priority": 1,
                    "action": "Validate access controls and source ownership.",
                    "rationale": "Deployment depends on governed source access.",
                }
            ],
            "assumptions": ["All source material is synthetic for this demonstration."],
            "information_gaps": ["Production workload and control effectiveness are unmeasured."],
        }
    )


def seed_demo_scenarios(session: Session) -> list[SeededDemoAssessment]:
    """Persist deterministic demo records without model or external network calls."""
    assessments = AssessmentRepository(session)
    reviews = RuntimeReviewRepository(session)
    governance = RuntimeGovernanceService(
        assessments=assessments,
        reviews=reviews,
        gate=RuntimeRiskGate(RuntimeRiskPolicy()),
    )
    scenarios = [
        (
            "high-risk-customer-pii",
            AssessmentRequest(
                company_name="Synthetic Retail Bank",
                industry="Financial services",
                business_problem="Draft customer responses using account context containing PII.",
                desired_outcome="Faster responses without unreviewed disclosure or advice.",
            ),
            True,
        ),
        (
            "low-risk-internal-assistant",
            AssessmentRequest(
                company_name="Synthetic Operations Company",
                industry="Business services",
                business_problem="Employees spend time locating internal procedures.",
                desired_outcome="Provide cited informational answers with no external action.",
            ),
            False,
        ),
    ]
    seeded = []
    for name, request, high_risk in scenarios:
        assessment_id = uuid4()
        assessments.create(
            assessment_id=assessment_id,
            company_name=request.company_name,
            industry=request.industry,
            business_problem=request.business_problem,
            request_payload=request.model_dump(mode="json"),
            created_by_subject="synthetic-demo-seed",
        )
        assessments.mark_processing(assessment_id)
        record = governance.process_candidate(
            assessment_id=assessment_id,
            result=_result(high_risk=high_risk),
            evidence=(),
            execution=DeterministicExecutionMetadata(),
            duration_ms=25 if high_risk else 10,
            signal_overrides={"evidence_required": False},
        )
        seeded.append(
            SeededDemoAssessment(
                scenario=name,
                assessment_id=assessment_id,
                status=record.status,
            )
        )
    assessments.commit()
    return seeded
