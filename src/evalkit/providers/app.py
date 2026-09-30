"""Targets for your own application: a shell command or an HTTP endpoint."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from pathlib import Path
from typing import Any

import httpx

from evalkit.config import CommandProviderConfig, HttpProviderConfig
from evalkit.providers.base import Provider, ProviderError, Request, Response
from evalkit.providers.http_common import dig, post_json
from evalkit.templating import has_placeholders, render, render_value


def _context(request: Request) -> dict[str, Any]:
    return {"prompt": request.prompt, "system": request.system or "", "vars": request.vars}


class CommandProvider(Provider):
    """Runs a program per task. The prompt goes to stdin, stdout is the output."""

    cache_by_default = False

    def __init__(self, config: CommandProviderConfig, base_dir: Path) -> None:
        self.config = config
        self.argv = (
            shlex.split(config.command) if isinstance(config.command, str) else list(config.command)
        )
        if not self.argv:
            raise ProviderError("command: empty command")
        self.cwd = (base_dir / config.cwd) if config.cwd else base_dir
        self.uses_stdin = not any(has_placeholders(arg) for arg in self.argv)

    @property
    def label(self) -> str:
        return f"command:{Path(self.argv[0]).name}"

    def identity(self) -> dict[str, Any]:
        return {"argv": self.argv, "cwd": str(self.cwd), "env": sorted(self.config.env)}

    async def complete(self, request: Request) -> Response:
        context = _context(request)
        argv = [render(arg, context) for arg in self.argv]
        env = {
            **os.environ,
            **self.config.env,
            "EVALKIT_SEED": str(request.seed),
            "EVALKIT_REPEAT": str(request.repeat),
        }
        if request.system:
            env["EVALKIT_SYSTEM"] = request.system
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=self.cwd,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise ProviderError(
                f"command: cannot start {argv[0]!r}: {exc.strerror or exc}"
            ) from exc
        stdin = request.prompt.encode() if self.uses_stdin else b""
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(stdin), timeout=self.config.timeout
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise ProviderError(
                f"command: timed out after {self.config.timeout}s", retriable=True
            ) from exc
        if process.returncode != 0:
            tail = stderr.decode(errors="replace").strip()[-500:]
            raise ProviderError(f"command: exited with status {process.returncode}: {tail}")
        return Response(text=stdout.decode(errors="replace").rstrip("\n"))


class HttpProvider(Provider):
    """Calls your HTTP endpoint with a templated JSON body."""

    cache_by_default = False

    def __init__(self, config: HttpProviderConfig, client: httpx.AsyncClient) -> None:
        self.config = config
        self.client = client

    @property
    def label(self) -> str:
        return f"http:{self.config.url}"

    def identity(self) -> dict[str, Any]:
        return self.config.model_dump(include={"url", "method", "body", "output_path"})

    async def complete(self, request: Request) -> Response:
        data = await post_json(
            self.client,
            self.config.method,
            self.config.url,
            headers=self.config.headers,
            body=render_value(self.config.body, _context(request)),
            timeout=self.config.timeout,
            provider="http",
        )
        if self.config.output_path:
            value = dig(data, self.config.output_path)
        elif isinstance(data, dict) and "output" in data:
            value = data["output"]
        else:
            value = data
        if isinstance(value, str):
            return Response(text=value)
        return Response(text=json.dumps(value, ensure_ascii=False))
