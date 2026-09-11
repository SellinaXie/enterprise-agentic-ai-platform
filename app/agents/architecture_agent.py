"""Toolless Solution Architecture Agent for V5."""

from typing import Protocol

from app.agents.architecture_prompt import (
    ARCHITECTURE_AGENT_SYSTEM_INSTRUCTIONS,
    build_architecture_input,
)
from app.agents.multi_agent_models import ArchitectureRecommendation, EvidenceBrief
from app.agents.structured_output import StructuredOutput
from app.schemas.assessment import AssessmentRequest


class ArchitectureAgent(Protocol):
    """Provider-neutral architecture specialist contract."""

    def analyze(
        self,
        request: AssessmentRequest,
        evidence_brief: EvidenceBrief,
    ) -> ArchitectureRecommendation: ...


class OpenAIArchitectureAgent:
    """Produce a typed architecture recommendation without receiving tools."""

    def __init__(self, structured_output: StructuredOutput) -> None:
        self._structured_output = structured_output

    def analyze(
        self,
        request: AssessmentRequest,
        evidence_brief: EvidenceBrief,
    ) -> ArchitectureRecommendation:
        return self._structured_output.generate(
            system=ARCHITECTURE_AGENT_SYSTEM_INSTRUCTIONS,
            user=build_architecture_input(request, evidence_brief),
            output_model=ArchitectureRecommendation,
        )
