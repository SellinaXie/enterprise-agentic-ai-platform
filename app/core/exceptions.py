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


class EmbeddingNotConfiguredError(ApplicationError):
    """Raised when knowledge embedding is requested without provider credentials."""

    error_code = "embedding_not_configured"
    public_message = (
        "Knowledge embeddings are unavailable because OPENAI_API_KEY is not configured."
    )


class EmbeddingProviderError(ApplicationError):
    """Raised when the embedding provider cannot complete a request."""

    error_code = "embedding_provider_error"
    public_message = "Knowledge embedding generation is temporarily unavailable. Please try again."


class InvalidEmbeddingError(ApplicationError):
    """Raised when embedding output has the wrong shape or invalid values."""

    error_code = "invalid_embedding"
    public_message = "The embedding service returned an invalid vector. Please try again."


class EmptyKnowledgeDocumentError(ApplicationError):
    """Raised when normalization leaves no ingestible text."""

    error_code = "empty_knowledge_document"
    public_message = "The knowledge document must contain non-whitespace text."


class KnowledgeDocumentNotFoundError(ApplicationError):
    """Raised when a requested knowledge document does not exist."""

    error_code = "knowledge_document_not_found"
    public_message = "The requested knowledge document was not found."


class KnowledgeStoreUnavailableError(ApplicationError):
    """Raised when PostgreSQL or pgvector cannot serve a knowledge operation."""

    error_code = "knowledge_store_unavailable"
    public_message = "The knowledge store is temporarily unavailable. Please try again."


class KnowledgePersistenceError(ApplicationError):
    """Raised when knowledge records cannot be persisted safely."""

    error_code = "knowledge_persistence_error"
    public_message = "The knowledge document could not be persisted. Please try again."
