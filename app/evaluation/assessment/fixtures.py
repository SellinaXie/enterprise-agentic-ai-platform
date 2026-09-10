"""Network-free execution adapter for version-controlled V7B mode fixtures."""

from copy import deepcopy

from app.evaluation.assessment.models import (
    AssessmentEvaluationCase,
    AssessmentEvaluationMode,
    AssessmentEvaluationOutput,
)


class DeterministicAssessmentFixtureExecutor:
    """Return declared outputs for each existing execution mode without provider calls."""

    def execute(
        self,
        case: AssessmentEvaluationCase,
        mode: AssessmentEvaluationMode,
    ) -> AssessmentEvaluationOutput:
        """Return an isolated copy so evaluation cannot mutate benchmark fixtures."""
        return deepcopy(case.fixtures[mode])
