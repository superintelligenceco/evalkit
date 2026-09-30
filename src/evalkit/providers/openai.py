"""OpenAI-compatible chat completions. Works with most gateways and local servers."""

from __future__ import annotations

from typing import Any

import httpx

from evalkit.config import OpenAIProviderConfig
from evalkit.providers.base import Provider, ProviderError, Request, Response, estimate_cost
from evalkit.providers.http_common import api_key, dig, post_json


class OpenAIProvider(Provider):
    def __init__(self, config: OpenAIProviderConfig, client: httpx.AsyncClient) -> None:
        self.config = config
        self.client = client

    @property
    def label(self) -> str:
        return f"openai:{self.config.model}"

    def identity(self) -> dict[str, Any]:
        return self.config.model_dump(
            include={"model", "base_url", "temperature", "max_tokens", "params"}
        )

    def build_body(self, request: Request) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        body: dict[str, Any] = {"model": self.config.model, "messages": messages}
        if self.config.temperature is not None:
            body["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            body["max_tokens"] = self.config.max_tokens
        body["seed"] = request.seed + request.repeat
        body.update(self.config.params)
        return body

    async def complete(self, request: Request) -> Response:
        headers = {"content-type": "application/json", **self.config.headers}
        key = api_key(self.config.api_key_env, "openai")
        if key:
            headers["authorization"] = f"Bearer {key}"
        data = await post_json(
            self.client,
            "POST",
            self.config.base_url.rstrip("/") + "/chat/completions",
            headers=headers,
            body=self.build_body(request),
            timeout=self.config.timeout,
            provider="openai",
        )
        if not isinstance(data, dict):
            raise ProviderError("openai: expected a JSON object in the response")
        content = dig(data, "choices.0.message.content")
        usage = data.get("usage") or {}
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        return Response(
            text=content if isinstance(content, str) else "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost(self.config.pricing, input_tokens, output_tokens),
        )
