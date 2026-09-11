"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from app import __version__
from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ApplicationError,
    AssessmentGenerationError,
    AssessmentNotFoundError,
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    DocumentParseError,
    EmbeddingNotConfiguredError,
    EmbeddingProviderError,
    EmptyFileError,
    EmptyKnowledgeDocumentError,
    EncryptedPDFError,
    FileTooLargeError,
    InvalidEmbeddingError,
    InvalidLLMResponseError,
    InvalidReviewTransitionError,
    InvalidUploadMetadataError,
    KnowledgeDocumentNotFoundError,
    KnowledgeGraphDisabledError,
    KnowledgeGraphExtractionError,
    KnowledgeGraphPersistenceError,
    KnowledgeGraphUnavailableError,
    KnowledgePersistenceError,
    KnowledgeStoreUnavailableError,
    LLMProviderError,
    OCRRequiredError,
    OpenAIClientNotConfiguredError,
    PersistenceError,
    RevisionLimitReachedError,
    RuntimeStateNotFoundError,
    TextDecodeError,
    UnsupportedFileTypeError,
)
from app.core.logging import configure_logging
from app.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure an application instance."""
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "application_started",
            extra={"environment": resolved_settings.environment},
        )
        yield
        logger.info("application_stopped")

    application = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        debug=resolved_settings.debug,
        lifespan=lifespan,
    )
    if settings is not None:
        application.dependency_overrides[get_settings] = lambda: resolved_settings

    @application.exception_handler(ApplicationError)
    async def handle_application_error(_: Request, exc: ApplicationError) -> JSONResponse:
        status_codes = {
            AssessmentNotFoundError: status.HTTP_404_NOT_FOUND,
            RuntimeStateNotFoundError: status.HTTP_404_NOT_FOUND,
            InvalidReviewTransitionError: status.HTTP_409_CONFLICT,
            RevisionLimitReachedError: status.HTTP_409_CONFLICT,
            OpenAIClientNotConfiguredError: status.HTTP_503_SERVICE_UNAVAILABLE,
            LLMProviderError: status.HTTP_502_BAD_GATEWAY,
            InvalidLLMResponseError: status.HTTP_502_BAD_GATEWAY,
            AssessmentGenerationError: status.HTTP_502_BAD_GATEWAY,
            DatabaseNotConfiguredError: status.HTTP_503_SERVICE_UNAVAILABLE,
            DatabaseUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
            PersistenceError: status.HTTP_503_SERVICE_UNAVAILABLE,
            EmbeddingNotConfiguredError: status.HTTP_503_SERVICE_UNAVAILABLE,
            EmbeddingProviderError: status.HTTP_502_BAD_GATEWAY,
            InvalidEmbeddingError: status.HTTP_502_BAD_GATEWAY,
            EmptyKnowledgeDocumentError: status.HTTP_422_UNPROCESSABLE_CONTENT,
            KnowledgeDocumentNotFoundError: status.HTTP_404_NOT_FOUND,
            KnowledgeStoreUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
            KnowledgePersistenceError: status.HTTP_503_SERVICE_UNAVAILABLE,
            KnowledgeGraphDisabledError: status.HTTP_503_SERVICE_UNAVAILABLE,
            KnowledgeGraphExtractionError: status.HTTP_502_BAD_GATEWAY,
            KnowledgeGraphPersistenceError: status.HTTP_503_SERVICE_UNAVAILABLE,
            KnowledgeGraphUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
            UnsupportedFileTypeError: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            FileTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
            EmptyFileError: status.HTTP_422_UNPROCESSABLE_CONTENT,
            InvalidUploadMetadataError: status.HTTP_422_UNPROCESSABLE_CONTENT,
            DocumentParseError: status.HTTP_422_UNPROCESSABLE_CONTENT,
            EncryptedPDFError: status.HTTP_422_UNPROCESSABLE_CONTENT,
            OCRRequiredError: status.HTTP_422_UNPROCESSABLE_CONTENT,
            TextDecodeError: status.HTTP_422_UNPROCESSABLE_CONTENT,
        }
        payload = ErrorResponse(error=ErrorDetail(code=exc.error_code, message=exc.public_message))
        return JSONResponse(
            status_code=status_codes.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR),
            content=payload.model_dump(mode="json"),
        )

    @application.middleware("http")
    async def log_requests(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid4()))
        started_at = perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                },
            )
            raise

        response.headers["x-request-id"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        return response

    application.include_router(health_router)
    application.include_router(api_router, prefix=resolved_settings.api_v1_prefix)
    return application


app = create_app()
