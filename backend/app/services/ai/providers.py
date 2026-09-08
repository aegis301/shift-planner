from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ProviderTurn:
    assistant_text: str | None
    tool_calls: list[ToolCall]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    parsed_json: dict[str, Any] | None = None


class LlmProvider(Protocol):
    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        api_key: str,
    ) -> ProviderTurn: ...


def anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["parameters"],
        }
        for tool in tools
    ]


def openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in tools
    ]


class AnthropicProvider:
    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        api_key: str,
    ) -> ProviderTurn:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            tools=anthropic_tools(tools),
            messages=messages,
        )
        tool_calls: list[ToolCall] = []
        texts: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {}))
                )
            elif getattr(block, "type", None) == "text" and getattr(block, "text", None):
                texts.append(block.text)
        usage = getattr(response, "usage", None)
        return ProviderTurn(
            assistant_text="\n".join(texts) or None,
            tool_calls=tool_calls,
            prompt_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )


class OpenAiProvider:
    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        api_key: str,
    ) -> ProviderTurn:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            tools=openai_tools(tools),
            messages=[{"role": "system", "content": system}, *messages],
        )
        choice = response.choices[0].message
        tool_calls: list[ToolCall] = []
        for call in choice.tool_calls or []:
            raw = call.function.arguments or "{}"
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            tool_calls.append(ToolCall(id=call.id, name=call.function.name, arguments=args))
        parsed = None
        if choice.content:
            try:
                loaded = json.loads(choice.content)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = None
        usage = getattr(response, "usage", None)
        return ProviderTurn(
            assistant_text=choice.content,
            tool_calls=tool_calls,
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            parsed_json=parsed,
        )


def provider_for(name: str) -> LlmProvider:
    if name == "anthropic":
        return AnthropicProvider()
    if name == "openai":
        return OpenAiProvider()
    raise ValueError("Unsupported AI provider")
