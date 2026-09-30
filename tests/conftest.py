from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from hypothesis import settings

from evalkit.config import Suite, parse_suite

# The nightly workflow sets HYPOTHESIS_PROFILE=nightly to search much harder than a pull request can.
settings.register_profile("nightly", max_examples=2000, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"

# Canned answers keyed by a substring of the user prompt.
ANSWERS = {
    "capital of Australia": "Canberra",
    "12 squared": "144",
    "Eiffel Tower": '```json\n{"city": "Paris", "country": "France"}\n```',
    "recursion": "Recursion is when something is defined using a smaller copy of itself.",
}


class FakeLLMServer:
    """A local OpenAI-compatible, Anthropic-compatible, and plain JSON endpoint."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.fail_next: list[int] = []
        self.answers = dict(ANSWERS)
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def _send(self, status: int, payload: Any) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                length = int(self.headers.get("content-length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                server.requests.append(
                    {"path": self.path, "headers": dict(self.headers), "body": body}
                )
                if server.fail_next:
                    status = server.fail_next.pop(0)
                    self._send(status, {"error": {"message": f"injected {status}"}})
                    return
                if self.path == "/v1/chat/completions":
                    prompt = body["messages"][-1]["content"]
                    self._send(
                        200,
                        {
                            "choices": [
                                {"message": {"role": "assistant", "content": server.answer(prompt)}}
                            ],
                            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                        },
                    )
                elif self.path == "/v1/messages":
                    prompt = body["messages"][-1]["content"]
                    self._send(
                        200,
                        {
                            "content": [{"type": "text", "text": server.answer(prompt)}],
                            "usage": {"input_tokens": 20, "output_tokens": 4},
                        },
                    )
                elif self.path == "/app":
                    self._send(200, {"data": {"answer": server.answer(body.get("question", ""))}})
                else:
                    self._send(404, {"error": "not found"})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )

    def answer(self, prompt: str) -> str:
        if "<rubric>" in prompt:
            return '{"score": 5, "reason": "meets the rubric"}'
        for needle, answer in self.answers.items():
            if needle in prompt:
                return answer
        return "I don't know."

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host!s}:{port}"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def fake_server() -> Iterator[FakeLLMServer]:
    server = FakeLLMServer()
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def make_suite(tmp_path: Path):
    """Build a validated Suite from a dict, rooted at tmp_path."""

    def build(data: dict[str, Any]) -> Suite:
        payload = {"name": "t", "target": {"provider": "mock"}, **data}
        payload.setdefault("settings", {})
        payload["settings"].setdefault("cache_path", str(tmp_path / "cache.sqlite"))
        payload["settings"].setdefault("retry_backoff", 0)
        return parse_suite(payload, base_dir=tmp_path)

    return build


# Hypothesis profiles: "ci" (default) stays fast, "nightly" digs deeper.
# Select one with HYPOTHESIS_PROFILE=nightly.
try:
    import os

    from hypothesis import settings

    settings.register_profile("ci", max_examples=100, deadline=None)
    settings.register_profile("nightly", max_examples=2000, deadline=None)
    settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
except ImportError:  # pragma: no cover - hypothesis is a dev dependency
    pass
