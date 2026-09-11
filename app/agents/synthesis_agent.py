"""Toolless final Synthesis Agent for V5."""

from typing import Protocol

from app.agents.multi_agent_models import (
    ArchitectureRecommendation,
    EvidenceBrief,
    RiskGovernanceReview,
)
from app.agents.structured_output import StructuredOutput
from app.agents.synthesis_prompt import (
    SYNTHESIS_AGENT_SYSTEM_INSTRUCTIONS,
    build_synthesis_input,
)
from app.schemas.assessment import AssessmentRequest, AssessmentResult


class SynthesisAgent(Protocol):
    """Provider-neutral final specialist contract."""

    def synthesize(
        self,
        *,
        request: AssessmentRequest,
        evidence_brief: EvidenceBrief,
        architecture: ArchitectureRecommendation | None,
        risk_governance: RiskGovernanceReview | None,
        degradation_reasons: list[str],
    ) -> AssessmentResult: ...


class OpenAISynthesisAgent:
    """Reconcile typed handoffs into the existing AssessmentResult schema."""

    def __init__(self, structured_output: StructuredOutput) -> None:
        self._structured_output = structured_output

    def synthesize(
        self,
        *,
        request: AssessmentRequest,
        evidence_brief: EvidenceBrief,
        architecture: ArchitectureRecommendation | None,
        risk_governance: RiskGovernanceReview | None,
        degradation_reasons: list[str],
    ) -> AssessmentResult:
        return self._structured_output.generate(
            system=SYNTHESIS_AGENT_SYSTEM_INSTRUCTIONS,
            user=build_synthesis_input(
                request=request,
                evidence_brief=evidence_brief,
                architecture=architecture,
                risk_governance=risk_governance,
                degradation_reasons=degradation_reasons,
            ),
            output_model=AssessmentResult,
        )
