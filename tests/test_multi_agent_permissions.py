"""Code-enforced V5 agent permission tests."""

from unittest.mock import Mock

from app.agents.multi_agent_models import MultiAgentName
from app.tools.models import SearchKnowledgeArguments, ToolExecutionResult
from app.tools.permissions import AgentToolPermissions
from app.tools.registry import ToolDefinition, ToolRegistry


def _registry(handler: Mock) -> ToolRegistry:
    return ToolRegistry(
        [
            ToolDefinition(
                name="search_knowledge",
                description="Search approved knowledge.",
                arguments_model=SearchKnowledgeArguments,
                handler=handler,
            )
        ]
    )


def test_only_evidence_agent_receives_approved_tool_schemas() -> None:
    permissions = AgentToolPermissions()
    registry = _registry(Mock())

    assert [
        item["name"] for item in permissions.schemas_for(MultiAgentName.EVIDENCE, registry)
    ] == ["search_knowledge"]
    assert permissions.schemas_for(MultiAgentName.ARCHITECTURE, registry) == []
    assert permissions.schemas_for(MultiAgentName.RISK_GOVERNANCE, registry) == []
    assert permissions.schemas_for(MultiAgentName.SYNTHESIS, registry) == []


def test_unauthorized_specialists_are_rejected_before_handler_execution() -> None:
    handler = Mock(
        return_value=ToolExecutionResult(
            tool_name="search_knowledge",
            success=True,
            summary="This must not run.",
        )
    )
    permissions = AgentToolPermissions()
    registry = _registry(handler)

    for agent in (
        MultiAgentName.ARCHITECTURE,
        MultiAgentName.RISK_GOVERNANCE,
        MultiAgentName.SYNTHESIS,
    ):
        result, _, argument_keys = permissions.execute(
            agent=agent,
            registry=registry,
            name="search_knowledge",
            raw_arguments={"query": "private query", "top_k": 1},
        )
        assert result.success is False
        assert result.error_code == "unauthorized_tool"
        assert result.summary == "The specialist is not authorized to use the requested tool."
        assert argument_keys == ("query", "top_k")

    handler.assert_not_called()
