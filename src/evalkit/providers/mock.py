"""Deterministic provider for offline tests, demos, and CI."""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections import Counter
from typing import Any

from evalkit.config import MockProviderConfig
from evalkit.providers.base import Provider, ProviderError, Request, Response, estimate_cost


def _tokens(text: str) -> int:
    return len(text.split())


class MockProvider(Provider):
    """Answers from regex rules. Same prompt, seed, and repeat always give the same output."""

    def __init__(self, config: MockProviderConfig) -> None:
        self.config = config
        self._rules = [(re.compile(rule.match), rule) for rule in config.responses]
        self._failures: Counter[tuple[str, int, int]] = Counter()

    @property
    def label(self) -> str:
        return f"mock:{self.config.model}"

    def identity(self) -> dict[str, Any]:
        return self.config.model_dump(exclude={"timeout", "pricing", "cache", "latency_ms"})

    def _roll(self, request: Request) -> float:
        digest = hashlib.sha256(
            f"{request.seed}:{request.repeat}:{request.prompt}".encode()
        ).digest()
        return int.from_bytes(digest[:8], "big") / 2**64

    async def complete(self, request: Request) -> Response:
        key = (request.prompt, request.seed, request.repeat)
        if self._failures[key] < self.config.fail_times:
            self._failures[key] += 1
            raise ProviderError("mock: simulated transient failure", retriable=True)
        if self.config.latency_ms:
            await asyncio.sleep(self.config.latency_ms / 1000)

        rule = next((r for pattern, r in self._rules if pattern.search(request.prompt)), None)
        flaky = self.config.flaky if rule is None or rule.flaky is None else rule.flaky
        if flaky and self._roll(request) < flaky:
            text = self.config.flaky_output
        elif rule is not None:
            text = rule.output
        else:
            text = request.prompt if self.config.default is None else self.config.default
        prompt_tokens = _tokens(request.prompt) + _tokens(request.system or "")
        output_tokens = _tokens(text)
        return Response(
            text=text,
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost(self.config.pricing, prompt_tokens, output_tokens),
        )
