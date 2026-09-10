"""Code-enforced V5 tool permissions layered over the existing V4 registry."""

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from app.agents.multi_agent_models import MultiAgentName
from app.tools.models import ToolExecutionResult
from app.tools.registry import ToolRegistry

EVIDENCE_TOOL_NAMES = frozenset(
    {"search_knowledge", "get_knowledge_document", "search_knowledge_graph"}
)


class AgentToolPermissions:
    """Expose tools only to the Evidence Agent and reject every other attempt."""

    _permissions = {
        MultiAgentName.EVIDENCE: EVIDENCE_TOOL_NAMES,
        MultiAgentName.ARCHITECTURE: frozenset(),
        MultiAgentName.RISK_GOVERNANCE: frozenset(),
        MultiAgentName.SYNTHESIS: frozenset(),
    }

    def schemas_for(
        self,
        agent: MultiAgentName,
        registry: ToolRegistry,
    ) -> list[dict[str, Any]]:
        """Return only schemas authorized for the named specialist."""
        allowed = self._permissions[agent]
        return [schema for schema in registry.schemas() if schema.get("name") in allowed]

    def execute(
        self,
        *,
        agent: MultiAgentName,
        registry: ToolRegistry,
        name: str,
        raw_arguments: Mapping[str, Any],
        cache: dict[str, ToolExecutionResult] | None = None,
    ) -> tuple[ToolExecutionResult, str, tuple[str, ...]]:
        """Reject unauthorized calls before any registered handler can execute."""
        if name not in self._permissions[agent]:
            argument_keys = tuple(sorted(str(key) for key in raw_arguments))
            fingerprint = hashlib.sha256(
                json.dumps(
                    {"agent": agent.value, "name": name, "arguments": dict(raw_arguments)},
                    default=str,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            return (
                ToolExecutionResult(
                    tool_name=name,
                    success=False,
                    summary="The specialist is not authorized to use the requested tool.",
                    error_code="unauthorized_tool",
                ),
                fingerprint,
                argument_keys,
            )
        return registry.execute(name, raw_arguments, cache=cache)
