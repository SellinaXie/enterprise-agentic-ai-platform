"""FastAPI application entry point."""

import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from http import HTTPStatus
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.context import get_request_id, reset_request_id, set_request_id
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
from app.db.session import dispose_database_resources
from app.schemas.errors import ErrorDetail, ErrorResponse
from app.services.llm import close_openai_client

logger = logging.getLogger(__name__)
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _safe_request_id(value: str | None, *, max_length: int) -> str:
    """Accept one bounded opaque identifier or generate a UUID."""
    if _request_id_is_valid(value, max_length=max_length):
        assert value is not None
        return value
    return str(uuid4())


def _request_id_is_valid(value: str | None, *, max_length: int) -> bool:
    return bool(
        value is not None
        and len(value) <= max_length
        and REQUEST_ID_PATTERN.fullmatch(value) is not None
    )


def _error_response(
    *,
    request_id: str | None,
    code: str,
    message: str,
    status_code: int,
    body_request_id: str | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorDetail(code=code, message=message),
        request_id=body_request_id,
    )
    response = JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json", exclude_none=True),
    )
    if request_id is not None:
        response.headers["x-request-id"] = request_id
    return response


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure an application instance."""
    resolved_settings = settings or get_settings()
    configure_logging(
        resolved_settings.log_level,
        include_exception_tracebacks=resolved_settings.log_exception_tracebacks,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "application_started",
            extra={"environment": resolved_settings.environment},
        )
        try:
            yield
        finally:
            close_openai_client()
            dispose_database_resources()
            logger.info("application_stopped")

    application = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        debug=resolved_settings.debug,
        lifespan=lifespan,
    )
    if settings is not None:
        application.dependency_overrides[get_settings] = lambda: resolved_settings

    if resolved_settings.parsed_cors_allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=resolved_settings.parsed_cors_allowed_origins,
            allow_credentials=resolved_settings.cors_allow_credentials,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Accept", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )
    if resolved_settings.parsed_trusted_hosts:
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=resolved_settings.parsed_trusted_hosts,
        )

    @application.exception_handler(ApplicationError)
    async def handle_application_error(request: Request, exc: ApplicationError) -> JSONResponse:
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
        return _error_response(
            request_id=getattr(request.state, "request_id", get_request_id()),
            body_request_id=(
                getattr(request.state, "request_id", None)
                if getattr(request.state, "request_id_supplied", False)
                else None
            ),
            code=exc.error_code,
            message=exc.public_message,
            status_code=status_codes.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR),
        )

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, _: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            request_id=getattr(request.state, "request_id", get_request_id()),
            body_request_id=(
                getattr(request.state, "request_id", None)
                if getattr(request.state, "request_id_supplied", False)
                else None
            ),
            code="request_validation_error",
            message="The request did not satisfy the API schema.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    @application.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        message = (
            HTTPStatus(exc.status_code).phrase
            if exc.status_code in HTTPStatus._value2member_map_
            else "HTTP error"
        )
        return _error_response(
            request_id=getattr(request.state, "request_id", get_request_id()),
            body_request_id=(
                getattr(request.state, "request_id", None)
                if getattr(request.state, "request_id_supplied", False)
                else None
            ),
            code="http_error",
            message=message,
            status_code=exc.status_code,
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_request_error",
            extra={"failure_type": type(exc).__name__},
        )
        return _error_response(
            request_id=getattr(request.state, "request_id", get_request_id()),
            body_request_id=(
                getattr(request.state, "request_id", None)
                if getattr(request.state, "request_id_supplied", False)
                else None
            ),
            code="internal_server_error",
            message="The request could not be completed.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @application.middleware("http")
    async def log_requests(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming_request_id = request.headers.get("x-request-id")
        request_id = _safe_request_id(
            incoming_request_id,
            max_length=resolved_settings.request_id_max_length,
        )
        request.state.request_id = request_id
        request.state.request_id_supplied = _request_id_is_valid(
            incoming_request_id,
            max_length=resolved_settings.request_id_max_length,
        )
        context_token = set_request_id(request_id)
        started_at = perf_counter()
        response: Response | None = None

        try:
            content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
            content_length = request.headers.get("content-length")
            if content_type == "application/json" and content_length is not None:
                try:
                    exceeds_limit = int(content_length) > (
                        resolved_settings.max_json_request_size_kb * 1024
                    )
                except ValueError:
                    exceeds_limit = True
                if exceeds_limit:
                    response = _error_response(
                        request_id=request_id,
                        body_request_id=(request_id if request.state.request_id_supplied else None),
                        code="request_too_large",
                        message="The JSON request exceeds the configured size limit.",
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    )
            if response is None:
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
        finally:
            if response is None:
                reset_request_id(context_token)

        try:
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
        finally:
            reset_request_id(context_token)

    application.include_router(health_router)
    application.include_router(api_router, prefix=resolved_settings.api_v1_prefix)
    return application


app = create_app()
