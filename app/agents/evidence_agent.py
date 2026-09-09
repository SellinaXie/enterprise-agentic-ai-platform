"""Bounded, tool-capable Evidence Agent for the V5 workflow."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

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
    ) -> None:
        self._model = model
        self._tools = tools
        self._permissions = permissions
        self._max_steps = max_steps
        self._max_tool_calls = max_tool_calls
        self._store_responses = store_responses
        self._client_provider = client_provider
        self._structured = OpenAIStructuredOutput(
            model=model,
            store_responses=store_responses,
            retry_limit=retry_limit,
            client_provider=client_provider,
        )

    def gather(self, request: AssessmentRequest) -> EvidenceAgentOutcome:
        """Run a finite one-tool-per-step loop, then emit a provenance-sanitized brief."""
        evidence: list[RetrievedEvidence] = []
        documents: list[ObservedKnowledgeDocument] = []
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
                )
            )
            self._merge_observations(evidence, documents, result)
        else:
            termination_reason = AgentTerminationReason.MAX_STEPS_REACHED

        raw_brief = self._structured.generate(
            system=EVIDENCE_BRIEF_SYSTEM_INSTRUCTIONS,
            user=build_evidence_brief_input(
                request=request,
                evidence=evidence,
                documents=documents,
            ),
            output_model=EvidenceBrief,
        )
        brief = self._sanitize_brief(raw_brief, evidence, documents)
        return EvidenceAgentOutcome(
            brief=brief,
            evidence=tuple(evidence),
            documents=tuple(documents),
            tool_history=tuple(history),
            steps_used=steps_used,
            termination_reason=termination_reason,
        )

    def _request_tool(
        self,
        *,
        request: AssessmentRequest,
        evidence: list[RetrievedEvidence],
        documents: list[ObservedKnowledgeDocument],
        history: list[ToolHistoryEntry],
        step: int,
    ) -> tuple[str, dict[str, object]] | None:
        try:
            response = self._client_provider().responses.create(
                model=self._model,
                input=[
                    {"role": "system", "content": EVIDENCE_AGENT_SYSTEM_INSTRUCTIONS},
                    {
                        "role": "user",
                        "content": build_evidence_decision_input(
                            request=request,
                            evidence=evidence,
                            documents=documents,
                            history=history,
                            step=step,
                            max_steps=self._max_steps,
                        ),
                    },
                ],
                tools=self._permissions.schemas_for(MultiAgentName.EVIDENCE, self._tools),
                tool_choice="auto",
                parallel_tool_calls=False,
                max_output_tokens=200,
                store=self._store_responses,
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
        result: ToolExecutionResult,
    ) -> None:
        existing_chunks = {item.chunk_id for item in evidence}
        evidence.extend(item for item in result.evidence if item.chunk_id not in existing_chunks)
        if result.document is not None and all(
            item.document_id != result.document.document_id for item in documents
        ):
            documents.append(result.document)

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
