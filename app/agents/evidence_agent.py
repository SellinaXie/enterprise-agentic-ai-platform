"""Bounded, tool-capable Evidence Agent for the V5 workflow."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter, sleep
from typing import Any, Protocol

from openai import OpenAI, OpenAIError

from app.agents.evidence_prompt import (
    EVIDENCE_AGENT_SYSTEM_INSTRUCTIONS,
    EVIDENCE_BRIEF_SYSTEM_INSTRUCTIONS,
    build_evidence_brief_input,
    build_evidence_decision_input,
)
from app.agents.models import AgentTerminationReason
from app.agents.multi_agent_models import EvidenceBrief, EvidenceItem, MultiAgentName
from app.agents.structured_output import OpenAIStructuredOutput
from app.core.exceptions import (
    InvalidLLMResponseError,
    LLMProviderError,
    OpenAIClientNotConfiguredError,
)
from app.models.knowledge import RetrievedEvidence
from app.models.knowledge_graph import GraphNeighborhood, GraphRetrievalExecutionMetadata
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import RetryPolicy
from app.runtime.resilience import run_with_retry
from app.schemas.assessment import AssessmentRequest
from app.tools.models import ObservedKnowledgeDocument, ToolExecutionResult, ToolHistoryEntry
from app.tools.permissions import AgentToolPermissions
from app.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class EvidenceAgentOutcome:
    """Typed evidence handoff plus safe observations from one bounded execution."""

    brief: EvidenceBrief
    evidence: tuple[RetrievedEvidence, ...]
    documents: tuple[ObservedKnowledgeDocument, ...]
    tool_history: tuple[ToolHistoryEntry, ...]
    steps_used: int
    termination_reason: AgentTerminationReason
    graph_neighborhoods: tuple[GraphNeighborhood, ...] = ()
    graph_retrieval: GraphRetrievalExecutionMetadata | None = None


class EvidenceAgent(Protocol):
    """Provider-neutral Evidence Agent contract consumed by LangGraph."""

    def gather(self, request: AssessmentRequest) -> EvidenceAgentOutcome: ...


class OpenAIEvidenceAgent:
    """Reuse the V4 tool registry/cache while producing a typed EvidenceBrief."""

    def __init__(
        self,
        *,
        model: str,
        tools: ToolRegistry,
        permissions: AgentToolPermissions,
        max_steps: int,
        max_tool_calls: int,
        store_responses: bool,
        retry_limit: int,
        client_provider: Callable[[], OpenAI],
        retry_base_delay_ms: int = 250,
        timeout_seconds: float | None = None,
        metrics: RuntimeMetricsRecorder | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._model = model
        self._tools = tools
        self._permissions = permissions
        self._max_steps = max_steps
        self._max_tool_calls = max_tool_calls
        self._store_responses = store_responses
        self._client_provider = client_provider
        self._retry_policy = RetryPolicy(
            max_retries=retry_limit,
            base_delay_ms=retry_base_delay_ms,
        )
        self._timeout_seconds = timeout_seconds
        self._metrics = metrics
        self._sleeper = sleeper
        self._structured = OpenAIStructuredOutput(
            model=model,
            store_responses=store_responses,
            retry_limit=retry_limit,
            retry_base_delay_ms=retry_base_delay_ms,
            timeout_seconds=timeout_seconds,
            metrics=metrics,
            sleeper=sleeper,
            client_provider=client_provider,
        )

    def gather(self, request: AssessmentRequest) -> EvidenceAgentOutcome:
        """Run a finite one-tool-per-step loop, then emit a provenance-sanitized brief."""
        evidence: list[RetrievedEvidence] = []
        documents: list[ObservedKnowledgeDocument] = []
        graph_neighborhoods: list[GraphNeighborhood] = []
        history: list[ToolHistoryEntry] = []
        cache: dict[str, ToolExecutionResult] = {}
        steps_used = 0
        termination_reason = AgentTerminationReason.AGENT_STOPPED

        for step in range(1, self._max_steps + 1):
            if len(history) >= self._max_tool_calls:
                termination_reason = AgentTerminationReason.MAX_TOOL_CALLS_REACHED
                break
            steps_used = step
            request_call = self._request_tool(
                request=request,
                evidence=evidence,
                documents=documents,
                history=history,
                graph_neighborhoods=graph_neighborhoods,
                step=step,
            )
            if request_call is None:
                termination_reason = AgentTerminationReason.AGENT_STOPPED
                break

            tool_name, arguments = request_call
            result, fingerprint, argument_keys = self._permissions.execute(
                agent=MultiAgentName.EVIDENCE,
                registry=self._tools,
                name=tool_name,
                raw_arguments=arguments,
                cache=cache,
            )
            history.append(
                ToolHistoryEntry(
                    step=step,
                    tool_name=tool_name,
                    success=result.success,
                    summary=result.summary,
                    argument_keys=argument_keys,
                    call_fingerprint=fingerprint,
                    cached=result.cached,
                    error_code=result.error_code,
                    graph_retrieval=result.graph_retrieval,
                )
            )
            self._merge_observations(evidence, documents, graph_neighborhoods, result)
        else:
            termination_reason = AgentTerminationReason.MAX_STEPS_REACHED

        raw_brief = self._structured.generate(
            system=EVIDENCE_BRIEF_SYSTEM_INSTRUCTIONS,
            user=build_evidence_brief_input(
                request=request,
                evidence=evidence,
                documents=documents,
                graph_neighborhoods=graph_neighborhoods,
            ),
            output_model=EvidenceBrief,
        )
        brief = self._sanitize_brief(raw_brief, evidence, documents)
        return EvidenceAgentOutcome(
            brief=brief,
            evidence=tuple(evidence),
            documents=tuple(documents),
            graph_neighborhoods=tuple(graph_neighborhoods),
            tool_history=tuple(history),
            steps_used=steps_used,
            termination_reason=termination_reason,
            graph_retrieval=_aggregate_graph_metadata(history),
        )

    def _request_tool(
        self,
        *,
        request: AssessmentRequest,
        evidence: list[RetrievedEvidence],
        documents: list[ObservedKnowledgeDocument],
        history: list[ToolHistoryEntry],
        graph_neighborhoods: list[GraphNeighborhood],
        step: int,
    ) -> tuple[str, dict[str, object]] | None:
        try:
            decision_input = build_evidence_decision_input(
                request=request,
                evidence=evidence,
                documents=documents,
                history=history,
                graph_neighborhoods=graph_neighborhoods,
                step=step,
                max_steps=self._max_steps,
            )

            def request_provider() -> Any:
                started = perf_counter()
                response = None
                kwargs: dict[str, Any] = {
                    "model": self._model,
                    "input": [
                        {"role": "system", "content": EVIDENCE_AGENT_SYSTEM_INSTRUCTIONS},
                        {"role": "user", "content": decision_input},
                    ],
                    "tools": self._permissions.schemas_for(MultiAgentName.EVIDENCE, self._tools),
                    "tool_choice": "auto",
                    "parallel_tool_calls": False,
                    "max_output_tokens": 200,
                    "store": self._store_responses,
                }
                if self._timeout_seconds is not None:
                    kwargs["timeout"] = self._timeout_seconds
                try:
                    response = self._client_provider().responses.create(**kwargs)
                    return response
                finally:
                    if self._metrics is not None:
                        self._metrics.record_model_call(
                            max(0, round((perf_counter() - started) * 1_000)), response
                        )

            response = run_with_retry(
                request_provider,
                policy=self._retry_policy,
                sleeper=self._sleeper,
                on_retry=(self._metrics.record_retry if self._metrics is not None else None),
            )
        except OpenAIClientNotConfiguredError:
            raise
        except OpenAIError as exc:
            raise LLMProviderError from exc
        except (TypeError, ValueError) as exc:
            raise InvalidLLMResponseError from exc

        calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        if not calls:
            return None
        call = calls[0]
        try:
            arguments = json.loads(call.arguments)
        except (json.JSONDecodeError, TypeError):
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        return str(call.name), arguments

    @staticmethod
    def _merge_observations(
        evidence: list[RetrievedEvidence],
        documents: list[ObservedKnowledgeDocument],
        graph_neighborhoods: list[GraphNeighborhood],
        result: ToolExecutionResult,
    ) -> None:
        existing_chunks = {item.chunk_id for item in evidence}
        evidence.extend(item for item in result.evidence if item.chunk_id not in existing_chunks)
        if result.document is not None and all(
            item.document_id != result.document.document_id for item in documents
        ):
            documents.append(result.document)
        if result.graph_neighborhood is not None:
            graph_neighborhoods.append(result.graph_neighborhood)

    @staticmethod
    def _sanitize_brief(
        brief: EvidenceBrief,
        evidence: list[RetrievedEvidence],
        documents: list[ObservedKnowledgeDocument],
    ) -> EvidenceBrief:
        allowed_documents = {item.document_id for item in evidence} | {
            item.document_id for item in documents
        }
        allowed_chunks = {item.chunk_id for item in evidence}
        items = []
        for item in brief.evidence_items:
            document_ids = [
                value for value in item.supporting_document_ids if value in allowed_documents
            ]
            chunk_ids = [value for value in item.supporting_chunk_ids if value in allowed_chunks]
            if not document_ids and not chunk_ids:
                continue
            items.append(
                EvidenceItem(
                    claim=item.claim,
                    supporting_document_ids=document_ids,
                    supporting_chunk_ids=chunk_ids,
                    relevance=item.relevance,
                    notes=item.notes,
                )
            )
        return brief.model_copy(
            update={
                "evidence_items": items,
                "retrieved_document_ids": sorted(allowed_documents, key=str),
                "retrieved_chunk_ids": sorted(allowed_chunks, key=str),
            }
        )


def _aggregate_graph_metadata(
    history: list[ToolHistoryEntry],
) -> GraphRetrievalExecutionMetadata | None:
    observations = [item.graph_retrieval for item in history if item.graph_retrieval is not None]
    if not observations:
        return None
    return GraphRetrievalExecutionMetadata(
        graph_retrieval_used=any(item.graph_retrieval_used for item in observations),
        matched_entity_count=sum(item.matched_entity_count for item in observations),
        relationship_count=sum(item.relationship_count for item in observations),
        graph_depth_used=max(item.graph_depth_used for item in observations),
        vector_evidence_count=sum(item.vector_evidence_count for item in observations),
        graph_evidence_count=sum(item.graph_evidence_count for item in observations),
        hybrid_evidence_count=sum(item.hybrid_evidence_count for item in observations),
        degraded_graph_mode=any(item.degraded_graph_mode for item in observations),
        graph_error_code=next(
            (item.graph_error_code for item in reversed(observations) if item.graph_error_code),
            None,
        ),
        vector_error_code=next(
            (item.vector_error_code for item in reversed(observations) if item.vector_error_code),
            None,
        ),
    )
