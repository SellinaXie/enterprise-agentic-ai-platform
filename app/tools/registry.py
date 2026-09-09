"""Explicit allowlist and typed execution boundary for V4 tools."""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.exceptions import ApplicationError
from app.tools.models import ToolExecutionResult

ToolHandler = Callable[[BaseModel], ToolExecutionResult]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """One statically registered, schema-constrained tool."""

    name: str
    description: str
    arguments_model: type[BaseModel]
    handler: ToolHandler

    def openai_schema(self) -> dict[str, Any]:
        """Return a strict Responses API function schema."""
        parameters = self.arguments_model.model_json_schema()
        parameters["additionalProperties"] = False
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": parameters,
            "strict": True,
        }


class ToolRegistry:
    """Reject every tool except the definitions supplied at construction time."""

    def __init__(self, definitions: list[ToolDefinition]) -> None:
        names = [definition.name for definition in definitions]
        if len(names) != len(set(names)):
            raise ValueError("Tool names must be unique")
        self._definitions = {definition.name: definition for definition in definitions}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def schemas(self) -> list[dict[str, Any]]:
        """Return only schemas for explicitly registered tools."""
        return [definition.openai_schema() for definition in self._definitions.values()]

    def execute(
        self,
        name: str,
        raw_arguments: Mapping[str, Any],
        *,
        cache: dict[str, ToolExecutionResult] | None = None,
    ) -> tuple[ToolExecutionResult, str, tuple[str, ...]]:
        """Validate and run one tool, reusing identical calls within this execution."""
        definition = self._definitions.get(name)
        argument_keys = tuple(sorted(str(key) for key in raw_arguments))
        if definition is None:
            return (
                ToolExecutionResult(
                    tool_name=name,
                    success=False,
                    summary="Requested tool is not in the approved tool registry.",
                    error_code="unknown_tool",
                ),
                self._fingerprint(name, raw_arguments),
                argument_keys,
            )

        try:
            arguments = definition.arguments_model.model_validate(dict(raw_arguments))
        except ValidationError:
            return (
                ToolExecutionResult(
                    tool_name=name,
                    success=False,
                    summary="Tool arguments did not match the approved schema.",
                    error_code="invalid_tool_arguments",
                ),
                self._fingerprint(name, raw_arguments),
                argument_keys,
            )

        normalized_arguments = arguments.model_dump(mode="json")
        fingerprint = self._fingerprint(name, normalized_arguments)
        if cache is not None and fingerprint in cache:
            return replace(cache[fingerprint], cached=True), fingerprint, argument_keys

        try:
            result = definition.handler(arguments)
        except ApplicationError as exc:
            result = ToolExecutionResult(
                tool_name=name,
                success=False,
                summary=exc.public_message,
                error_code=exc.error_code,
            )
        except Exception:
            result = ToolExecutionResult(
                tool_name=name,
                success=False,
                summary="The approved tool could not complete the request.",
                error_code="tool_execution_error",
            )

        if cache is not None:
            cache[fingerprint] = result
        return result, fingerprint, argument_keys

    @staticmethod
    def _fingerprint(name: str, arguments: Mapping[str, Any]) -> str:
        serialized = json.dumps(
            {"name": name, "arguments": dict(arguments)},
            default=str,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
