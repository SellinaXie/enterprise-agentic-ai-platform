"""Reusable test data builders."""

from uuid import UUID

from app.agents.multi_agent_models import (
    ArchitectureRecommendation,
    EvidenceBrief,
    EvidenceItem,
    GovernanceOversight,
    GovernanceRisk,
    RiskGovernanceReview,
    SpecialistConfidence,
)
from app.schemas.assessment import AssessmentResult


def build_evidence_brief(
    *,
    document_id: UUID | None = None,
    chunk_id: UUID | None = None,
) -> EvidenceBrief:
    """Return a synthetic typed evidence handoff with optional provenance."""
    evidence_items = []
    if document_id is not None and chunk_id is not None:
        evidence_items.append(
            EvidenceItem(
                claim="Authorized staff retain final approval for high-impact recommendations.",
                supporting_document_ids=[document_id],
                supporting_chunk_ids=[chunk_id],
                relevance="Directly defines the required human decision boundary.",
                notes="Synthetic test evidence.",
            )
        )
    return EvidenceBrief(
        summary=(
            "A synthetic governance source requires human approval."
            if evidence_items
            else "No relevant external evidence was retrieved."
        ),
        evidence_items=evidence_items,
        evidence_gaps=[] if evidence_items else ["No external evidence was available."],
        confidence=SpecialistConfidence.HIGH if evidence_items else SpecialistConfidence.LOW,
        retrieved_document_ids=[document_id] if document_id is not None else [],
        retrieved_chunk_ids=[chunk_id] if chunk_id is not None else [],
    )


def build_architecture_recommendation() -> ArchitectureRecommendation:
    """Return a representative typed architecture handoff."""
    return ArchitectureRecommendation(
        recommended_pattern="llm_assisted_workflow",
        architecture_summary="A bounded RAG assistant prepares review packages for analysts.",
        components=["Existing workflow", "Retrieval service", "Structured LLM generation"],
        data_flow=["Request", "Retrieve policy evidence", "Draft", "Human approval"],
        integrations=["Existing case-management API"],
        complexity="medium",
        implementation_assumptions=["A case-management API is available."],
        alternatives_considered=["Deterministic document templates"],
        why_simpler_options_are_or_are_not_sufficient=(
            "Templates do not cover variable evidence, while autonomous action is unnecessary."
        ),
        confidence="high",
    )


def build_risk_governance_review() -> RiskGovernanceReview:
    """Return a representative typed risk/governance handoff."""
    return RiskGovernanceReview(
        overall_risk="high",
        risks=[
            GovernanceRisk(
                category="compliance",
                description="A generated summary could omit decision-relevant evidence.",
                severity="high",
                mitigation="Require human review with source links before any decision.",
            )
        ],
        required_controls=["Role-based access", "Source-linked analyst review"],
        human_oversight=GovernanceOversight(
            review_required=True,
            decisions_requiring_review=["Credit and compliance decisions"],
            rationale="The workflow affects regulated lending decisions.",
        ),
        auditability_requirements=["Log source references and reviewer approval"],
        unresolved_questions=["Applicable retention policy"],
        confidence="high",
    )


def build_assessment_result() -> AssessmentResult:
    """Return a representative valid structured assessment."""
    return AssessmentResult.model_validate(
        {
            "executive_summary": (
                "Loan review is slowed by manual document collection and risk analysis. "
                "An LLM-assisted workflow could help analysts prepare review packages while "
                "leaving regulated decisions with authorized staff."
            ),
            "problem_analysis": {
                "core_problem": "Manual evidence gathering delays loan decisions.",
                "current_process_weaknesses": [
                    "Analysts collect information across documents manually.",
                    "Review preparation is difficult to standardize.",
                ],
                "key_bottlenecks": ["Document collection", "Risk-summary preparation"],
            },
            "ai_suitability": {
                "level": "high",
                "rationale": (
                    "The process contains document-heavy assistive work, but final decisions "
                    "require compliance review."
                ),
            },
            "recommended_use_cases": [
                {
                    "name": "Loan review package preparation",
                    "description": "Extract and organize supplied application evidence.",
                    "expected_business_value": (
                        "Reduce analyst preparation effort and improve consistency."
                    ),
                    "complexity": "medium",
                    "priority": "high",
                }
            ],
            "recommended_solution": {
                "pattern": "llm_assisted_workflow",
                "description": (
                    "Use an LLM to prepare cited review summaries inside the existing process."
                ),
                "rationale": (
                    "Assistance is useful, while autonomous credit decisions are not justified."
                ),
            },
            "risks": [
                {
                    "category": "compliance",
                    "description": "Generated summaries could omit decision-relevant evidence.",
                    "severity": "high",
                    "mitigation": (
                        "Require analyst review and retain links to the source evidence."
                    ),
                }
            ],
            "human_oversight": {
                "review_recommended": True,
                "decisions_requiring_review": ["Credit and compliance decisions"],
                "rationale": "The supplied process affects regulated lending decisions.",
            },
            "next_steps": [
                {
                    "priority": 1,
                    "action": "Map required loan evidence and approval controls.",
                    "rationale": "The workflow cannot be designed safely without them.",
                }
            ],
            "assumptions": [
                "Analysts can review generated material before a decision is recorded."
            ],
            "information_gaps": ["Document volumes and current processing-time baseline"],
        }
    )
