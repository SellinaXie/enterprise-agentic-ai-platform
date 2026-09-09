"""Safe application-level exceptions exposed through the API."""


class ApplicationError(Exception):
    """Base class for failures with a stable public API representation."""

    error_code = "application_error"
    public_message = "The request could not be completed."

    def __init__(self) -> None:
        super().__init__(self.public_message)


class OpenAIClientNotConfiguredError(ApplicationError):
    """Raised when an AI assessment is requested without an API key."""

    error_code = "openai_not_configured"
    public_message = "AI assessments are unavailable because OPENAI_API_KEY is not configured."


class LLMProviderError(ApplicationError):
    """Raised when the upstream model provider cannot complete a request."""

    error_code = "llm_provider_error"
    public_message = "AI assessment generation is temporarily unavailable. Please try again."


class InvalidLLMResponseError(ApplicationError):
    """Raised when a model response does not satisfy the assessment schema."""

    error_code = "invalid_llm_response"
    public_message = "The AI service returned an invalid assessment. Please try again."


class AssessmentGenerationError(ApplicationError):
    """Raised when assessment generation fails unexpectedly."""

    error_code = "assessment_generation_error"
    public_message = "AI assessment generation failed unexpectedly. Please try again."


class DatabaseNotConfiguredError(ApplicationError):
    """Raised when persistence is requested without a database URL."""

    error_code = "database_not_configured"
    public_message = "Assessment persistence is unavailable because DATABASE_URL is not configured."


class DatabaseUnavailableError(ApplicationError):
    """Raised when the configured state database cannot be reached."""

    error_code = "database_unavailable"
    public_message = "Assessment persistence is temporarily unavailable. Please try again."


class PersistenceError(ApplicationError):
    """Raised when a database operation cannot be completed safely."""

    error_code = "persistence_error"
    public_message = "The assessment could not be persisted. Please try again."


class AssessmentNotFoundError(ApplicationError):
    """Raised when a requested assessment does not exist."""

    error_code = "assessment_not_found"
    public_message = "The requested assessment was not found."
