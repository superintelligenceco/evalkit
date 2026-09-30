"""Provider interface shared by models and apps under test."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from evalkit.config import Pricing


@dataclass(frozen=True)
class Request:
    prompt: str
    system: str | None = None
    seed: int = 0
    repeat: int = 0
    vars: dict[str, Any] = field(default_factory=dict)


@dataclass
class Response:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: float = 0.0
    cached: bool = False


class ProviderError(RuntimeError):
    """A failed call. Retriable errors (timeouts, 429, 5xx) are retried by the runner."""

    def __init__(self, message: str, *, retriable: bool = False) -> None:
        super().__init__(message)
        self.retriable = retriable


def estimate_cost(
    pricing: Pricing | None, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    if pricing is None or input_tokens is None or output_tokens is None:
        return None
    return (
        input_tokens * pricing.input_per_mtok + output_tokens * pricing.output_per_mtok
    ) / 1_000_000


def is_retriable_status(status: int) -> bool:
    return status in (408, 409, 425, 429) or status >= 500


class Provider(abc.ABC):
    """Turns a rendered prompt into text."""

    #: Whether responses are cached by default. Models: yes. Your own app: no.
    cache_by_default: bool = True

    @property
    @abc.abstractmethod
    def label(self) -> str:
        """Short human-readable name, such as ``openai:gpt-4o-mini``."""

    @abc.abstractmethod
    def identity(self) -> dict[str, Any]:
        """Settings that change the output. Used in the cache key. Never include secrets."""

    @abc.abstractmethod
    async def complete(self, request: Request) -> Response:
        """Return the output for ``request`` or raise :class:`ProviderError`."""

    async def aclose(self) -> None:  # noqa: B027 - optional hook
        """Release network resources."""
