"""Toolless Risk & Governance Agent for V5."""

from typing import Protocol

from app.agents.multi_agent_models import EvidenceBrief, RiskGovernanceReview
from app.agents.risk_governance_prompt import (
    RISK_GOVERNANCE_AGENT_SYSTEM_INSTRUCTIONS,
    build_risk_governance_input,
)
from app.agents.structured_output import StructuredOutput
from app.schemas.assessment import AssessmentRequest


class RiskGovernanceAgent(Protocol):
    """Provider-neutral governance specialist contract."""

    def review(
        self,
        request: AssessmentRequest,
        evidence_brief: EvidenceBrief,
    ) -> RiskGovernanceReview: ...


class OpenAIRiskGovernanceAgent:
    """Produce an independent typed control review without receiving tools."""

    def __init__(self, structured_output: StructuredOutput) -> None:
        self._structured_output = structured_output

    def review(
        self,
        request: AssessmentRequest,
        evidence_brief: EvidenceBrief,
    ) -> RiskGovernanceReview:
        return self._structured_output.generate(
            system=RISK_GOVERNANCE_AGENT_SYSTEM_INSTRUCTIONS,
            user=build_risk_governance_input(request, evidence_brief),
            output_model=RiskGovernanceReview,
        )
