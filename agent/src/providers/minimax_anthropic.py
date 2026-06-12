"""MiniMax Anthropic-compatible Messages adapter.

This is intentionally narrow: Vibe's AgentLoop speaks OpenAI-style messages and
function-tool definitions, while MiniMax recommends its Anthropic-compatible
Messages endpoint for M3 agent workflows. The adapter translates only the
message, tool-call, tool-result, and usage shapes the AgentLoop needs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import httpx

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_BASE_URL = "https://api.minimaxi.com/anthropic"


@dataclass
class MiniMaxAnthropicMessage:
    """Small LangChain-like message object parsed by ``ChatLLM``."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    additional_kwargs: dict[str, Any] = field(default_factory=dict)
    response_metadata: dict[str, Any] = field(default_factory=dict)
    usage_metadata: dict[str, int] | None = None

    def __add__(self, other: "MiniMaxAnthropicMessage") -> "MiniMaxAnthropicMessage":
        usage = other.usage_metadata or self.usage_metadata
        reasoning = (
            self.additional_kwargs.get("reasoning_content", "")
            + other.additional_kwargs.get("reasoning_content", "")
        )
        additional_kwargs = {**self.additional_kwargs, **other.additional_kwargs}
        if reasoning:
            additional_kwargs["reasoning_content"] = reasoning
        return MiniMaxAnthropicMessage(
            content=f"{self.content or ''}{other.content or ''}",
            tool_calls=[*self.tool_calls, *other.tool_calls],
            additional_kwargs=additional_kwargs,
            response_metadata={**self.response_metadata, **other.response_metadata},
            usage_metadata=usage,
        )


class MiniMaxAnthropicLLM:
    """Minimal Anthropic Messages client compatible with ``ChatLLM``."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        temperature: float = 0.01,
        timeout: int = 120,
        max_retries: int = 2,
        max_tokens: int = 8192,
        tools: list[dict[str, Any]] | None = None,
        thinking: str = "disabled",
        service_tier: str = "standard",
    ) -> None:
        if not api_key:
            raise RuntimeError("MINIMAX_API_KEY is not set")
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.strip().rstrip("/") or DEFAULT_BASE_URL
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.tools = tools or []
        self.thinking = thinking
        self.service_tier = service_tier

    def bind_tools(self, tools: list[dict[str, Any]]) -> "MiniMaxAnthropicLLM":
        return MiniMaxAnthropicLLM(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=self.temperature,
            timeout=self.timeout,
            max_retries=self.max_retries,
            max_tokens=self.max_tokens,
            tools=tools,
            thinking=self.thinking,
            service_tier=self.service_tier,
        )

    def stream(
        self,
        messages: list[dict[str, Any]],
        config: Optional[dict[str, Any]] = None,
    ) -> Iterable[MiniMaxAnthropicMessage]:
        yield self.invoke(messages, config=config)

    def invoke(
        self,
        messages: list[dict[str, Any]],
        config: Optional[dict[str, Any]] = None,
    ) -> MiniMaxAnthropicMessage:
        timeout = int((config or {}).get("timeout") or self.timeout)
        body = self._body(messages)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=True) as client:
                    response = client.post(self._messages_url(), headers=self._headers(), json=body)
                if response.status_code >= 400:
                    raise RuntimeError(f"MiniMax Anthropic HTTP {response.status_code}: {response.text[:500]}")
                payload = response.json()
                return _message_from_payload(payload)
            except Exception as exc:  # noqa: BLE001 - preserve provider failure for AgentLoop.
                last_error = exc
                if attempt >= self.max_retries:
                    raise
        raise RuntimeError(str(last_error) if last_error else "MiniMax Anthropic request failed")

    def _messages_url(self) -> str:
        if self.base_url.endswith("/v1/messages"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/messages"
        return f"{self.base_url}/v1/messages"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
        }

    def _body(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        system, anthropic_messages = _convert_messages(messages)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if system:
            body["system"] = system
        tools = _convert_tools(self.tools)
        if tools:
            body["tools"] = tools
            body["tool_choice"] = {"type": "auto"}
        if self.thinking in {"disabled", "adaptive"}:
            body["thinking"] = {"type": self.thinking}
        if self.service_tier in {"standard", "priority"}:
            body["service_tier"] = self.service_tier
        return body


def build_minimax_anthropic_llm(*, model: str, temperature: float, timeout: int, max_retries: int) -> MiniMaxAnthropicLLM:
    """Construct the MiniMax Anthropic adapter from environment variables."""
    return MiniMaxAnthropicLLM(
        model=model,
        api_key=os.getenv("MINIMAX_API_KEY", "") or os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv("MINIMAX_BASE_URL", "") or DEFAULT_BASE_URL,
        temperature=temperature,
        timeout=timeout,
        max_retries=max_retries,
        max_tokens=int(os.getenv("MINIMAX_MAX_TOKENS", "8192")),
        thinking=os.getenv("MINIMAX_THINKING", "disabled").strip().lower(),
        service_tier=os.getenv("MINIMAX_SERVICE_TIER", "standard").strip().lower(),
    )


def _convert_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "")
        if role == "system":
            text = _text_from_content(message.get("content"))
            if text:
                system_parts.append(text)
            continue
        if role == "assistant":
            blocks = _assistant_blocks(message)
            _append_message(converted, "assistant", blocks)
            continue
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": str(message.get("tool_call_id") or ""),
                "content": _text_from_content(message.get("content")),
            }
            _append_message(converted, "user", [block])
            continue
        if role == "user":
            text = _text_from_content(message.get("content"))
            _append_message(converted, "user", [{"type": "text", "text": text}])
    if not converted:
        converted.append({"role": "user", "content": [{"type": "text", "text": ""}]})
    return "\n\n".join(system_parts), converted


def _append_message(target: list[dict[str, Any]], role: str, blocks: list[dict[str, Any]]) -> None:
    clean_blocks = [block for block in blocks if block.get("type")]
    if not clean_blocks:
        clean_blocks = [{"type": "text", "text": ""}]
    if target and target[-1].get("role") == role:
        target[-1].setdefault("content", []).extend(clean_blocks)
    else:
        target.append({"role": role, "content": clean_blocks})


def _assistant_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    text = _text_from_content(message.get("content"))
    if text:
        blocks.append({"type": "text", "text": text})
    for tool_call in message.get("tool_calls") or []:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function") or {}
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        blocks.append(
            {
                "type": "tool_use",
                "id": str(tool_call.get("id") or ""),
                "name": name,
                "input": _decode_args(function.get("arguments")),
            }
        )
    return blocks


def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools:
        function = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        converted.append(
            {
                "name": name,
                "description": str(function.get("description") or ""),
                "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return converted


def _message_from_payload(payload: dict[str, Any]) -> MiniMaxAnthropicMessage:
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in payload.get("content") or []:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text_parts.append(str(block.get("text") or ""))
        elif block_type == "thinking":
            reasoning_parts.append(str(block.get("thinking") or ""))
        elif block_type == "tool_use":
            tool_calls.append(
                {
                    "id": str(block.get("id") or ""),
                    "name": str(block.get("name") or ""),
                    "args": block.get("input") if isinstance(block.get("input"), dict) else {},
                }
            )
    reasoning = "".join(reasoning_parts)
    usage = _usage_metadata(payload.get("usage"))
    return MiniMaxAnthropicMessage(
        content="".join(text_parts),
        tool_calls=tool_calls,
        additional_kwargs={"reasoning_content": reasoning} if reasoning else {},
        response_metadata={"finish_reason": _finish_reason(payload.get("stop_reason"))},
        usage_metadata=usage,
    )


def _usage_metadata(raw: Any) -> dict[str, int] | None:
    if not isinstance(raw, dict):
        return None
    input_tokens = _as_int(raw.get("input_tokens"))
    output_tokens = _as_int(raw.get("output_tokens"))
    cache_creation = _as_int(raw.get("cache_creation_input_tokens"))
    cache_read = _as_int(raw.get("cache_read_input_tokens"))
    total_tokens = input_tokens + output_tokens + cache_creation + cache_read
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
        "total_tokens": total_tokens,
    }


def _finish_reason(stop_reason: Any) -> str:
    return {
        "end_turn": "stop",
        "tool_use": "tool_calls",
        "max_tokens": "length",
    }.get(str(stop_reason or ""), "stop")


def _text_from_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "\n".join(part for part in parts if part)
    return str(content)


def _decode_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        decoded = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
