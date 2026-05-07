import json
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass
class TextBlock:
    type: str
    text: str


@dataclass
class ToolUseBlock:
    type: str
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class MessageResponse:
    content: list[Any]
    stop_reason: str


class _MessagesAPI:
    def __init__(self, client: OpenAI):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8000,
        **kwargs: Any,
    ) -> MessageResponse:
        chat_messages = _to_openai_messages(system, messages)
        tool_defs = _to_openai_tools(tools or [])

        resp = self._client.chat.completions.create(
            model=model,
            messages=chat_messages,
            tools=tool_defs or None,
            max_tokens=max_tokens,
            **kwargs,
        )

        choice = resp.choices[0]
        message = choice.message
        blocks: list[Any] = []

        if getattr(message, "content", None):
            blocks.append(TextBlock(type="text", text=message.content))

        for tool_call in getattr(message, "tool_calls", None) or []:
            args = tool_call.function.arguments or "{}"
            try:
                parsed = json.loads(args)
            except json.JSONDecodeError:
                parsed = {"raw_arguments": args}
            blocks.append(
                ToolUseBlock(
                    type="tool_use",
                    id=tool_call.id,
                    name=tool_call.function.name,
                    input=parsed,
                )
            )

        stop_reason = "tool_use" if getattr(message, "tool_calls", None) else "end_turn"
        return MessageResponse(content=blocks, stop_reason=stop_reason)


class Anthropic:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, **kwargs: Any):
        resolved_base_url = (
            base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("ANTHROPIC_BASE_URL")
        )
        resolved_api_key = (
            api_key or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        )

        if not resolved_api_key:
            raise ValueError(
                "Missing API key. Set OPENAI_API_KEY (preferred) or ANTHROPIC_API_KEY."
            )

        self._client = OpenAI(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            **kwargs,
        )
        self.messages = _MessagesAPI(self._client)


def _to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted = []
    for tool in tools:
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get(
                        "input_schema", {"type": "object", "properties": {}}
                    ),
                },
            }
        )
    return converted


def _to_openai_messages(
    system: str | None, messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    if system:
        converted.append({"role": "system", "content": system})

    for message in messages:
        converted.extend(_convert_message(message["role"], message["content"]))

    return converted


def _convert_message(role: str, content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"role": role, "content": content}]

    if not isinstance(content, list):
        return [{"role": role, "content": str(content)}]

    if role == "assistant":
        text_parts = []
        tool_calls = []
        for block in content:
            block_type = _get_value(block, "type")
            if block_type == "text":
                text = _get_value(block, "text")
                if text:
                    text_parts.append(text)
            elif block_type == "tool_use":
                tool_calls.append(
                    {
                        "id": _get_value(block, "id"),
                        "type": "function",
                        "function": {
                            "name": _get_value(block, "name"),
                            "arguments": json.dumps(_get_value(block, "input") or {}),
                        },
                    }
                )

        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": "\n".join(text_parts) if text_parts else "",
        }
        if tool_calls:
            assistant_message["tool_calls"] = tool_calls
        return [assistant_message]

    if role == "user":
        converted = []
        text_parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                if text_parts:
                    converted.append({"role": "user", "content": "\n".join(text_parts)})
                    text_parts = []
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": str(block.get("content", "")),
                    }
                )
            else:
                text = _get_value(block, "text")
                if text:
                    text_parts.append(text)

        if text_parts:
            converted.append({"role": "user", "content": "\n".join(text_parts)})
        return converted or [{"role": "user", "content": ""}]

    return [{"role": role, "content": str(content)}]


def _get_value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
