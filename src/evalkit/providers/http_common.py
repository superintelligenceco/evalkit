"""Shared HTTP plumbing for network providers."""

from __future__ import annotations

import os
from typing import Any

import httpx

from evalkit.providers.base import ProviderError, is_retriable_status


def api_key(env_name: str | None, provider: str) -> str | None:
    if env_name is None:
        return None
    value = os.environ.get(env_name)
    if not value:
        raise ProviderError(f"{provider}: environment variable {env_name} is not set")
    return value


async def post_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    body: Any,
    timeout: float,
    provider: str,
) -> Any:
    """Send a JSON request and return the decoded JSON (or text) response."""
    try:
        response = await client.request(
            method,
            url,
            headers=headers,
            json=body if method != "GET" else None,
            params=body if method == "GET" and isinstance(body, dict) else None,
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise ProviderError(
            f"{provider}: request timed out after {timeout}s", retriable=True
        ) from exc
    except httpx.TransportError as exc:
        raise ProviderError(f"{provider}: {exc.__class__.__name__}: {exc}", retriable=True) from exc

    if response.status_code >= 400:
        detail = response.text[:500].strip()
        raise ProviderError(
            f"{provider}: HTTP {response.status_code}: {detail}",
            retriable=is_retriable_status(response.status_code),
        )
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(f"{provider}: invalid JSON in response") from exc
    return response.text


def dig(data: Any, path: str) -> Any:
    """Follow a dotted path such as ``choices.0.message.content``."""
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif (
            isinstance(current, list)
            and part.lstrip("-").isdigit()
            and -len(current) <= int(part) < len(current)
        ):
            current = current[int(part)]
        else:
            raise ProviderError(f"response has no field '{path}' (stopped at '{part}')")
    return current
