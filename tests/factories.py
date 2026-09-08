"""Reusable test data builders."""

from app.schemas.assessment import AssessmentResult


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
