"""Assessment domain types."""

from enum import StrEnum


class AssessmentStatus(StrEnum):
    """Lifecycle states supported by an assessment."""

    COMPLETED = "completed"


class SuitabilityLevel(StrEnum):
    """Overall suitability of the business problem for an AI-enabled solution."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ComplexityLevel(StrEnum):
    """Relative delivery complexity of a recommended use case."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PriorityLevel(StrEnum):
    """Relative implementation priority."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SolutionPattern(StrEnum):
    """High-level solution patterns available to an assessment."""

    DETERMINISTIC_AUTOMATION = "deterministic_automation"
    LLM_ASSISTED_WORKFLOW = "llm_assisted_workflow"
    RAG_DECISION_SUPPORT = "rag_decision_support"
    TOOL_USING_AGENT = "tool_using_agent"
    AGENTIC_WORKFLOW = "agentic_workflow"


class RiskCategory(StrEnum):
    """Enterprise risk categories considered by an assessment."""

    PRIVACY = "privacy"
    SECURITY = "security"
    HALLUCINATION = "hallucination"
    COMPLIANCE = "compliance"
    DATA_QUALITY = "data_quality"
    EXPLAINABILITY = "explainability"
    OPERATIONAL = "operational"


class RiskSeverity(StrEnum):
    """Severity of an identified enterprise risk."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
