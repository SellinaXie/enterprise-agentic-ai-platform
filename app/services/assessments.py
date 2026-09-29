"""Assessment application service."""

import logging
from time import perf_counter
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.agents.models import AssessmentExecutionMetadata, DeterministicExecutionMetadata
from app.agents.multi_agent_models import MultiAgentExecutionMetadata
from app.core.context import get_request_id
from app.core.exceptions import (
    ApplicationError,
    AssessmentGenerationError,
    AssessmentNotFoundError,
    DatabaseUnavailableError,
    PersistenceError,
)
from app.identity.models import AuthenticatedPrincipal
from app.models.assessment import ExternalEvidenceStatus
from app.models.knowledge import RAGPreparation, RetrievedEvidence
from app.models.knowledge_graph import HybridRAGPreparation
from app.models.persisted_assessment import PersistedAssessment
from app.schemas.assessment import (
    AssessmentFailure,
    AssessmentRequest,
    AssessmentResponse,
    AssessmentResult,
)
from app.services.assessment_prompt import AssessmentPrompt, build_assessment_prompt
from app.services.execution_router import (
    ExecutionMode,
    ExecutionRoutingDecision,
    FallbackReasonCode,
    ResolvedExecutionRoute,
    RoutingReasonCode,
)

logger = logging.getLogger(__name__)


class AssessmentGenerator(Protocol):
    """Provider-independent interface for structured assessment generation."""

    def generate(self, prompt: AssessmentPrompt) -> AssessmentResult:
        """Generate a validated assessment result."""
        ...


class AssessmentRepositoryProtocol(Protocol):
    """Persistence operations required by the assessment workflow."""

    def create(
        self,
        *,
        assessment_id: UUID,
        company_name: str,
        industry: str,
        business_problem: str,
        request_payload: dict[str, Any],
        created_by_subject: str | None = None,
    ) -> PersistedAssessment: ...

    def get_by_id(self, assessment_id: UUID) -> PersistedAssessment | None: ...

    def mark_processing(self, assessment_id: UUID) -> PersistedAssessment | None: ...

    def mark_completed(
        self,
        assessment_id: UUID,
        result_payload: dict[str, Any],
        execution_metadata: dict[str, Any] | None = None,
    ) -> PersistedAssessment | None: ...

    def mark_pending_review(
        self,
        assessment_id: UUID,
        execution_metadata: dict[str, Any] | None = None,
    ) -> PersistedAssessment | None: ...

    def mark_failed(
        self,
        assessment_id: UUID,
        *,
        error_code: str,
        error_message: str,
    ) -> PersistedAssessment | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class AssessmentRAGProtocol(Protocol):
    """RAG preparation required by the assessment workflow when enabled."""

    def prepare(self, request: AssessmentRequest) -> RAGPreparation | HybridRAGPreparation: ...


ExecutionMetadata = (
    DeterministicExecutionMetadata | AssessmentExecutionMetadata | MultiAgentExecutionMetadata
)


class AgentWorkflowOutput(Protocol):
    """Provider-neutral result returned by an agentic workflow."""

    result: AssessmentResult
    evidence: tuple[RetrievedEvidence, ...]
    execution: AssessmentExecutionMetadata | MultiAgentExecutionMetadata


class AgenticAssessmentWorkflowProtocol(Protocol):
    """Optional V4 workflow invoked only behind its feature flag."""

    def run(
        self,
        *,
        assessment_id: str,
        request: AssessmentRequest,
    ) -> AgentWorkflowOutput: ...


class MultiAgentAssessmentWorkflowProtocol(Protocol):
    """Optional V5 workflow, which has precedence over the V4 path."""

    def run(
        self,
        *,
        assessment_id: str,
        request: AssessmentRequest,
    ) -> AgentWorkflowOutput: ...


class RuntimeGovernanceProtocol(Protocol):
    """Optional post-generation decision boundary enabled only for V7C."""

    def process_candidate(
        self,
        *,
        assessment_id: UUID,
        result: AssessmentResult,
        evidence: tuple[RetrievedEvidence, ...],
        execution: ExecutionMetadata,
        duration_ms: int,
        provenance_valid: bool = True,
        retrieval_duration_ms: int | None = None,
    ) -> PersistedAssessment: ...


class ExecutionRouterProtocol(Protocol):
    """Per-request workflow selection boundary."""

    def route(self, request: AssessmentRequest) -> ExecutionRoutingDecision: ...


class AssessmentService:
    """Coordinate generation and explicit persistence transaction boundaries."""

    def __init__(
        self,
        generator: AssessmentGenerator,
        repository: AssessmentRepositoryProtocol,
        rag_service: AssessmentRAGProtocol | None = None,
        agentic_workflow: AgenticAssessmentWorkflowProtocol | None = None,
        multi_agent_workflow: MultiAgentAssessmentWorkflowProtocol | None = None,
        runtime_governance: RuntimeGovernanceProtocol | None = None,
        execution_router: ExecutionRouterProtocol | None = None,
    ) -> None:
        self._generator = generator
        self._repository = repository
        self._rag_service = rag_service
        self._agentic_workflow = agentic_workflow
        self._multi_agent_workflow = multi_agent_workflow
        self._runtime_governance = runtime_governance
        self._execution_router = execution_router

    def generate_assessment(
        self,
        request: AssessmentRequest,
        *,
        principal: AuthenticatedPrincipal | None = None,
    ) -> AssessmentResponse:
        """Persist lifecycle state around synchronous structured generation."""
        assessment_id = uuid4()
        log_context = {"assessment_id": str(assessment_id)}

        request_payload = request.model_dump(mode="json")
        try:
            create_arguments: dict[str, Any] = {
                "assessment_id": assessment_id,
                "company_name": request.company_name,
                "industry": request.industry,
                "business_problem": request.business_problem,
                "request_payload": request_payload,
            }
            if principal is not None:
                create_arguments["created_by_subject"] = principal.subject
            self._repository.create(
                **create_arguments,
            )
            self._repository.commit()
        except SQLAlchemyError as exc:
            raise self._handle_database_error(exc) from exc

        logger.info("assessment_record_created", extra={**log_context, "status": "pending"})

        try:
            processing_record = self._repository.mark_processing(assessment_id)
            if processing_record is None:
                raise PersistenceError
            self._repository.commit()
        except SQLAlchemyError as exc:
            raise self._handle_database_error(exc) from exc

        logger.info("assessment_marked_processing", extra={**log_context, "status": "processing"})
        logger.info("assessment_generation_started", extra=log_context)
        generation_started = perf_counter()

        evidence: tuple[RetrievedEvidence, ...] = ()
        routing = self._route_execution(request)
        routing_metadata: dict[str, Any] = {}
        if self._execution_router is not None:
            routing_metadata = {
                "preferred_execution_mode": routing.preferred_execution_mode.value,
                "routing_reason_codes": [
                    reason.value for reason in routing.routing_reason_codes
                ],
                "fallback_reason_codes": [
                    reason.value for reason in routing.fallback_reason_codes
                ],
            }
        execution: ExecutionMetadata = DeterministicExecutionMetadata(**routing_metadata)
        retrieval_duration_ms: int | None = None
        logger.info(
            "assessment_execution_routed",
            extra={
                **log_context,
                "preferred_execution_mode": routing.preferred_execution_mode.value,
                "execution_mode": routing.execution_mode.value,
                "routing_reason_codes": routing_metadata.get("routing_reason_codes", []),
                "fallback_reason_codes": routing_metadata.get("fallback_reason_codes", []),
            },
        )
        try:
            if routing.execution_mode == ExecutionMode.MULTI_AGENT:
                assert self._multi_agent_workflow is not None
                workflow_result = self._multi_agent_workflow.run(
                    assessment_id=str(assessment_id),
                    request=request,
                )
                result = workflow_result.result
                evidence = workflow_result.evidence
                execution = workflow_result.execution.model_copy(
                    update=routing_metadata
                )
            elif routing.execution_mode == ExecutionMode.SINGLE_AGENT:
                assert self._agentic_workflow is not None
                workflow_result = self._agentic_workflow.run(
                    assessment_id=str(assessment_id),
                    request=request,
                )
                result = workflow_result.result
                evidence = workflow_result.evidence
                execution = workflow_result.execution.model_copy(
                    update=routing_metadata
                )
            else:
                rag_context = None
                if self._rag_service is not None:
                    retrieval_started = perf_counter()
                    try:
                        preparation = self._rag_service.prepare(request)
                    finally:
                        retrieval_duration_ms = max(
                            0, round((perf_counter() - retrieval_started) * 1_000)
                        )
                    evidence = preparation.evidence
                    rag_context = preparation.context
                    graph_retrieval = getattr(preparation, "graph_retrieval", None)
                    if graph_retrieval is not None:
                        execution = execution.model_copy(
                            update={"graph_retrieval": graph_retrieval}
                        )
                prompt = (
                    build_assessment_prompt(request, rag_context)
                    if rag_context is not None
                    else build_assessment_prompt(request)
                )
                result = self._generator.generate(prompt)
            provenance_valid = self._provenance_is_valid(result, evidence)
            result = self._apply_grounding_metadata(result, evidence)
            request_id = get_request_id()
            if request_id is not None:
                execution = execution.model_copy(update={"request_id": request_id})
        except ApplicationError as exc:
            self._persist_failure(
                assessment_id,
                error_code=exc.error_code,
                error_message=exc.public_message,
            )
            logger.warning(
                "assessment_failed",
                extra={**log_context, "error_code": exc.error_code},
            )
            raise
        except Exception as exc:
            unexpected_error = AssessmentGenerationError()
            self._persist_failure(
                assessment_id,
                error_code=unexpected_error.error_code,
                error_message=unexpected_error.public_message,
            )
            logger.error(
                "assessment_failed",
                extra={
                    **log_context,
                    "error_code": unexpected_error.error_code,
                    "generation_error_type": type(exc).__name__,
                },
            )
            raise unexpected_error from exc

        try:
            if self._runtime_governance is not None:
                completed_record = self._runtime_governance.process_candidate(
                    assessment_id=assessment_id,
                    result=result,
                    evidence=evidence,
                    execution=execution,
                    duration_ms=max(0, round((perf_counter() - generation_started) * 1_000)),
                    provenance_valid=provenance_valid,
                    retrieval_duration_ms=retrieval_duration_ms,
                )
            else:
                completed_record = self._repository.mark_completed(
                    assessment_id,
                    result.model_dump(mode="json"),
                    execution.model_dump(mode="json"),
                )
            if completed_record is None:
                raise PersistenceError
            self._repository.commit()
        except SQLAlchemyError as exc:
            raise self._handle_database_error(exc) from exc

        logger.info(
            "assessment_result_persisted",
            extra={**log_context, "status": completed_record.status.value},
        )
        logger.info(
            "grounded_assessment_generated",
            extra={**log_context, "retrieval_count": len(evidence)},
        )
        logger.info(
            "assessment_generation_finalized",
            extra={**log_context, "status": completed_record.status.value},
        )
        return self._to_response(completed_record)

    def _route_execution(self, request: AssessmentRequest) -> ResolvedExecutionRoute:
        if self._execution_router is None:
            if self._multi_agent_workflow is not None:
                mode = ExecutionMode.MULTI_AGENT
            elif self._agentic_workflow is not None:
                mode = ExecutionMode.SINGLE_AGENT
            else:
                mode = ExecutionMode.DETERMINISTIC
            return ResolvedExecutionRoute(
                preferred_execution_mode=mode,
                execution_mode=mode,
                routing_reason_codes=[RoutingReasonCode.LEGACY_FLAG_SELECTION],
            )

        decision = self._execution_router.route(request)
        preferred = decision.preferred_execution_mode
        actual = preferred
        fallback_reasons: list[FallbackReasonCode] = []
        if preferred == ExecutionMode.MULTI_AGENT and self._multi_agent_workflow is None:
            fallback_reasons.append(FallbackReasonCode.MULTI_AGENT_CAPABILITY_UNAVAILABLE)
            if self._agentic_workflow is not None:
                actual = ExecutionMode.SINGLE_AGENT
                fallback_reasons.append(FallbackReasonCode.FALLBACK_TO_SINGLE_AGENT)
            else:
                actual = ExecutionMode.DETERMINISTIC
                fallback_reasons.extend(
                    [
                        FallbackReasonCode.SINGLE_AGENT_CAPABILITY_UNAVAILABLE,
                        FallbackReasonCode.FALLBACK_TO_DETERMINISTIC,
                    ]
                )
        elif preferred == ExecutionMode.SINGLE_AGENT and self._agentic_workflow is None:
            actual = ExecutionMode.DETERMINISTIC
            fallback_reasons.extend(
                [
                    FallbackReasonCode.SINGLE_AGENT_CAPABILITY_UNAVAILABLE,
                    FallbackReasonCode.FALLBACK_TO_DETERMINISTIC,
                ]
            )

        return ResolvedExecutionRoute(
            preferred_execution_mode=preferred,
            execution_mode=actual,
            routing_reason_codes=decision.reason_codes,
            fallback_reason_codes=fallback_reasons,
        )

    def get_assessment(self, assessment_id: UUID) -> AssessmentResponse:
        """Retrieve and validate persisted assessment state by ID."""
        logger.info("assessment_retrieval_requested", extra={"assessment_id": str(assessment_id)})
        try:
            record = self._repository.get_by_id(assessment_id)
        except SQLAlchemyError as exc:
            raise self._handle_database_error(exc) from exc

        if record is None:
            logger.info("assessment_not_found", extra={"assessment_id": str(assessment_id)})
            raise AssessmentNotFoundError
        return self._to_response(record)

    def _persist_failure(
        self,
        assessment_id: UUID,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        try:
            failed_record = self._repository.mark_failed(
                assessment_id,
                error_code=error_code,
                error_message=error_message,
            )
            if failed_record is None:
                raise PersistenceError
            self._repository.commit()
        except SQLAlchemyError as exc:
            raise self._handle_database_error(exc) from exc
        logger.info(
            "assessment_failure_persisted",
            extra={
                "assessment_id": str(assessment_id),
                "status": "failed",
                "error_code": error_code,
            },
        )

    def _handle_database_error(self, exc: SQLAlchemyError) -> ApplicationError:
        try:
            self._repository.rollback()
        except SQLAlchemyError as rollback_exc:
            logger.error(
                "database_rollback_failed",
                extra={"database_error_type": type(rollback_exc).__name__},
            )

        logger.error(
            "database_failure",
            extra={"database_error_type": type(exc).__name__},
        )
        if isinstance(exc, OperationalError):
            return DatabaseUnavailableError()
        return PersistenceError()

    @staticmethod
    def _apply_grounding_metadata(
        result: AssessmentResult,
        evidence: tuple[RetrievedEvidence, ...],
    ) -> AssessmentResult:
        allowed = {(item.document_id, item.chunk_id) for item in evidence}
        seen: set[tuple[UUID, UUID]] = set()
        references = []
        for reference in result.source_references:
            key = (reference.document_id, reference.chunk_id)
            if key in allowed and key not in seen:
                references.append(reference)
                seen.add(key)
        status = (
            ExternalEvidenceStatus.RETRIEVED if evidence else ExternalEvidenceStatus.NOT_RETRIEVED
        )
        return result.model_copy(
            update={
                "external_evidence_status": status,
                "source_references": references,
            }
        )

    @staticmethod
    def _provenance_is_valid(
        result: AssessmentResult,
        evidence: tuple[RetrievedEvidence, ...],
    ) -> bool:
        allowed = {(item.document_id, item.chunk_id) for item in evidence}
        return all(
            (reference.document_id, reference.chunk_id) in allowed
            for reference in result.source_references
        )

    @staticmethod
    def _to_response(record: PersistedAssessment) -> AssessmentResponse:
        try:
            request = AssessmentRequest.model_validate(record.request_payload)
            result = (
                AssessmentResult.model_validate(record.result_payload)
                if record.result_payload is not None
                else None
            )
            execution = AssessmentService._parse_execution_metadata(record.execution_metadata)
        except ValidationError as exc:
            raise PersistenceError from exc

        error = None
        if record.error_code is not None and record.error_message is not None:
            error = AssessmentFailure(code=record.error_code, message=record.error_message)

        return AssessmentResponse(
            assessment_id=record.assessment_id,
            status=record.status,
            input=request,
            result=result,
            execution=execution,
            error=error,
            created_at=record.created_at,
            updated_at=record.updated_at,
            completed_at=record.completed_at,
        )

    @staticmethod
    def _parse_execution_metadata(payload: dict[str, Any] | None) -> ExecutionMetadata | None:
        """Read new mode markers plus historical nullable and V4 `agentic` metadata."""
        if payload is None:
            return None
        mode = payload.get("execution_mode")
        if mode == "deterministic":
            return DeterministicExecutionMetadata.model_validate(payload)
        if mode == "multi_agent":
            return MultiAgentExecutionMetadata.model_validate(payload)
        return AssessmentExecutionMetadata.model_validate(payload)
