"""Safe application-level exceptions exposed through the API."""


class ApplicationError(Exception):
    """Base class for failures with a stable public API representation."""

    error_code = "application_error"
    public_message = "The request could not be completed."

    def __init__(self) -> None:
        super().__init__(self.public_message)


class AuthenticationRequiredError(ApplicationError):
    """Raised for missing, invalid, expired, or untrusted bearer credentials."""

    error_code = "authentication_required"
    public_message = "Valid bearer authentication is required."


class PermissionDeniedError(ApplicationError):
    """Raised when an authenticated principal lacks the required role."""

    error_code = "permission_denied"
    public_message = "The authenticated principal is not permitted to perform this action."


class OpenAIClientNotConfiguredError(ApplicationError):
    """Raised when an AI assessment is requested without an API key."""

    error_code = "openai_not_configured"
    public_message = "AI assessments are unavailable because OPENAI_API_KEY is not configured."


class ModelProviderNotConfiguredError(ApplicationError):
    """Raised when the selected structured-model provider lacks its credential."""

    error_code = "model_provider_not_configured"
    public_message = "AI assessments are unavailable because the model provider is not configured."


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


class RuntimeStateNotFoundError(ApplicationError):
    """Raised when an assessment has no V7C checkpoint."""

    error_code = "runtime_state_not_found"
    public_message = "Runtime governance state is not available for this assessment."


class InvalidReviewTransitionError(ApplicationError):
    """Raised for duplicate or out-of-order human actions."""

    error_code = "invalid_review_transition"
    public_message = "The requested human review action is not valid in the current state."


class RevisionLimitReachedError(ApplicationError):
    """Raised when the bounded review loop has been exhausted."""

    error_code = "revision_limit_reached"
    public_message = "The maximum number of human-requested revisions has been reached."


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


class KnowledgeGraphDisabledError(ApplicationError):
    """Raised when an opt-in graph operation is requested while V6 is disabled."""

    error_code = "knowledge_graph_disabled"
    public_message = "Knowledge graph operations are not enabled."


class KnowledgeGraphExtractionError(ApplicationError):
    """Raised when graph candidates cannot be validated safely."""

    error_code = "knowledge_graph_extraction_error"
    public_message = "Knowledge graph extraction could not produce valid grounded data."


class KnowledgeGraphPersistenceError(ApplicationError):
    """Raised when graph records cannot be persisted atomically."""

    error_code = "knowledge_graph_persistence_error"
    public_message = "The knowledge graph could not be persisted. Please try again."


class KnowledgeGraphUnavailableError(ApplicationError):
    """Raised when bounded graph retrieval cannot access its persistence layer."""

    error_code = "knowledge_graph_unavailable"
    public_message = "Knowledge graph retrieval is temporarily unavailable. Please try again."


class UnsupportedFileTypeError(ApplicationError):
    """Raised when upload extension, MIME type, or signature is not allowlisted."""

    error_code = "unsupported_file_type"
    public_message = "The uploaded file type is not supported or does not match its content."


class FileTooLargeError(ApplicationError):
    """Raised before an upload grows beyond the configured in-memory limit."""

    error_code = "file_too_large"
    public_message = "The uploaded file exceeds the configured size limit."


class EmptyFileError(ApplicationError):
    """Raised when an upload contains no bytes."""

    error_code = "empty_file"
    public_message = "The uploaded file is empty."


class InvalidUploadMetadataError(ApplicationError):
    """Raised when multipart metadata is not a valid bounded JSON object."""

    error_code = "invalid_upload_metadata"
    public_message = "Upload metadata must be a valid JSON object."


class DocumentParseError(ApplicationError):
    """Raised when an allowlisted document cannot be parsed safely."""

    error_code = "document_parse_failed"
    public_message = "The uploaded document could not be parsed."


class EncryptedPDFError(ApplicationError):
    """Raised when an encrypted PDF cannot be processed without credentials."""

    error_code = "encrypted_pdf"
    public_message = "Encrypted PDF files are not supported."


class OCRRequiredError(ApplicationError):
    """Raised when a PDF has insufficient digitally extractable text."""

    error_code = "ocr_required"
    public_message = "The PDF requires OCR because it has insufficient extractable text."


class TextDecodeError(ApplicationError):
    """Raised when a text upload is not valid UTF-8."""

    error_code = "text_decode_failed"
    public_message = "The text document is not valid UTF-8."
