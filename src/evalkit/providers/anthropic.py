"""Anthropic Messages API."""

from __future__ import annotations

from typing import Any

import httpx

from evalkit.config import AnthropicProviderConfig
from evalkit.providers.base import Provider, ProviderError, Request, Response, estimate_cost
from evalkit.providers.http_common import api_key, post_json


class AnthropicProvider(Provider):
    def __init__(self, config: AnthropicProviderConfig, client: httpx.AsyncClient) -> None:
        self.config = config
        self.client = client

    @property
    def label(self) -> str:
        return f"anthropic:{self.config.model}"

    def identity(self) -> dict[str, Any]:
        return self.config.model_dump(
            include={"model", "base_url", "temperature", "max_tokens", "params"}
        )

    def build_body(self, request: Request) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system:
            body["system"] = request.system
        if self.config.temperature is not None:
            body["temperature"] = self.config.temperature
        body.update(self.config.params)
        return body

    async def complete(self, request: Request) -> Response:
        headers = {
            "content-type": "application/json",
            "anthropic-version": self.config.anthropic_version,
            **self.config.headers,
        }
        key = api_key(self.config.api_key_env, "anthropic")
        if key:
            headers["x-api-key"] = key
        data = await post_json(
            self.client,
            "POST",
            self.config.base_url.rstrip("/") + "/v1/messages",
            headers=headers,
            body=self.build_body(request),
            timeout=self.config.timeout,
            provider="anthropic",
        )
        if not isinstance(data, dict) or not isinstance(data.get("content"), list):
            raise ProviderError("anthropic: response has no 'content' list")
        text = "".join(
            block.get("text", "")
            for block in data["content"]
            if isinstance(block, dict) and block.get("type") == "text"
        )
        usage = data.get("usage") or {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        return Response(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost(self.config.pricing, input_tokens, output_tokens),
        )
