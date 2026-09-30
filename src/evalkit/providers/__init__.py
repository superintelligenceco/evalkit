"""Providers turn a rendered prompt into an output string."""

from __future__ import annotations

from pathlib import Path

import httpx

from evalkit.config import (
    AnthropicProviderConfig,
    CommandProviderConfig,
    HttpProviderConfig,
    MockProviderConfig,
    OpenAIProviderConfig,
    ProviderConfig,
)
from evalkit.providers.anthropic import AnthropicProvider
from evalkit.providers.app import CommandProvider, HttpProvider
from evalkit.providers.base import Provider, ProviderError, Request, Response
from evalkit.providers.mock import MockProvider
from evalkit.providers.openai import OpenAIProvider

__all__ = [
    "Provider",
    "ProviderError",
    "Request",
    "Response",
    "build_provider",
]


def build_provider(
    config: ProviderConfig, *, base_dir: Path, client: httpx.AsyncClient
) -> Provider:
    """Create the provider described by ``config``."""
    if isinstance(config, MockProviderConfig):
        return MockProvider(config)
    if isinstance(config, OpenAIProviderConfig):
        return OpenAIProvider(config, client)
    if isinstance(config, AnthropicProviderConfig):
        return AnthropicProvider(config, client)
    if isinstance(config, CommandProviderConfig):
        return CommandProvider(config, base_dir)
    if isinstance(config, HttpProviderConfig):
        return HttpProvider(config, client)
    raise TypeError(f"unsupported provider config: {type(config).__name__}")  # pragma: no cover
