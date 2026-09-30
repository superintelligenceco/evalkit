import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from pydantic import TypeAdapter

from evalkit.config import ProviderConfig
from evalkit.providers import ProviderError, Request, build_provider
from evalkit.providers.base import estimate_cost, is_retriable_status
from evalkit.providers.http_common import dig

ADAPTER = TypeAdapter(ProviderConfig)


def complete(spec, request, *, base_dir=Path(".")):
    async def go():
        async with httpx.AsyncClient() as client:
            provider = build_provider(
                ADAPTER.validate_python(spec), base_dir=base_dir, client=client
            )
            try:
                return provider, await provider.complete(request)
            finally:
                await provider.aclose()

    return asyncio.run(go())


# mock ------------------------------------------------------------------------


def test_mock_rules_default_and_echo():
    spec = {"provider": "mock", "responses": [{"match": "cap.*France", "output": "Paris"}]}
    _, response = complete(spec, Request(prompt="capital of France?"))
    assert response.text == "Paris"
    _, echo = complete(spec, Request(prompt="unmatched"))
    assert echo.text == "unmatched"
    _, fallback = complete({**spec, "default": "no idea"}, Request(prompt="unmatched"))
    assert fallback.text == "no idea"


def test_mock_counts_tokens_and_prices():
    spec = {
        "provider": "mock",
        "default": "one two",
        "pricing": {"input_per_mtok": 1e6, "output_per_mtok": 2e6},
    }
    _, response = complete(spec, Request(prompt="a b c", system="s"))
    assert (response.input_tokens, response.output_tokens) == (4, 2)
    assert response.cost_usd == pytest.approx(4 + 4)


def test_mock_flakiness_is_deterministic():
    spec = {"provider": "mock", "default": "ok", "flaky": 0.5, "flaky_output": "bad"}
    outputs = [complete(spec, Request(prompt="q", repeat=i))[1].text for i in range(40)]
    again = [complete(spec, Request(prompt="q", repeat=i))[1].text for i in range(40)]
    assert outputs == again
    assert 5 < outputs.count("bad") < 35


def test_mock_fail_times_raises_retriable_errors():
    async def go():
        async with httpx.AsyncClient() as client:
            config = ADAPTER.validate_python({"provider": "mock", "default": "ok", "fail_times": 2})
            provider = build_provider(config, base_dir=Path("."), client=client)
            errors = []
            for _ in range(2):
                with pytest.raises(ProviderError) as info:
                    await provider.complete(Request(prompt="q"))
                errors.append(info.value.retriable)
            return errors, await provider.complete(Request(prompt="q"))

    errors, response = asyncio.run(go())
    assert errors == [True, True]
    assert response.text == "ok"


# openai / anthropic ----------------------------------------------------------


def test_openai_request_and_response(fake_server, monkeypatch):
    monkeypatch.setenv("TEST_KEY", "sk-test")
    spec = {
        "provider": "openai",
        "model": "m",
        "base_url": fake_server.url + "/v1/",
        "api_key_env": "TEST_KEY",
        "temperature": 0,
        "max_tokens": 50,
        "params": {"top_p": 0.5},
        "pricing": {"input_per_mtok": 1, "output_per_mtok": 2},
    }
    provider, response = complete(
        spec, Request(prompt="12 squared?", system="be brief", seed=3, repeat=1)
    )
    assert response.text == "144"
    assert (response.input_tokens, response.output_tokens) == (10, 5)
    assert response.cost_usd == pytest.approx(20 / 1e6)
    sent = fake_server.requests[0]
    assert sent["path"] == "/v1/chat/completions"
    assert sent["headers"]["authorization"] == "Bearer sk-test"
    assert sent["body"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert sent["body"]["seed"] == 4
    assert sent["body"]["top_p"] == 0.5
    assert provider.label == "openai:m"
    assert "sk-test" not in str(provider.identity())


def test_openai_missing_key_is_an_error(monkeypatch):
    monkeypatch.delenv("NO_SUCH_KEY", raising=False)
    with pytest.raises(ProviderError, match="NO_SUCH_KEY is not set"):
        complete(
            {"provider": "openai", "model": "m", "api_key_env": "NO_SUCH_KEY"}, Request(prompt="x")
        )


def test_anthropic_request_and_response(fake_server, monkeypatch):
    monkeypatch.setenv("TEST_KEY", "ak-test")
    spec = {
        "provider": "anthropic",
        "model": "m",
        "base_url": fake_server.url,
        "api_key_env": "TEST_KEY",
        "temperature": 0.2,
    }
    _, response = complete(spec, Request(prompt="capital of Australia", system="sys"))
    assert response.text == "Canberra"
    assert (response.input_tokens, response.output_tokens) == (20, 4)
    sent = fake_server.requests[0]
    assert sent["path"] == "/v1/messages"
    assert sent["headers"]["x-api-key"] == "ak-test"
    assert sent["headers"]["anthropic-version"] == "2023-06-01"
    assert sent["body"]["system"] == "sys"
    assert sent["body"]["max_tokens"] == 1024


@pytest.mark.parametrize(
    ("status", "retriable"), [(429, True), (503, True), (400, False), (401, False)]
)
def test_http_errors_carry_retriable_flag(fake_server, status, retriable):
    fake_server.fail_next = [status]
    spec = {
        "provider": "openai",
        "model": "m",
        "base_url": fake_server.url + "/v1",
        "api_key_env": None,
    }
    with pytest.raises(ProviderError) as info:
        complete(spec, Request(prompt="x"))
    assert f"HTTP {status}" in str(info.value)
    assert info.value.retriable is retriable


def test_connection_error_is_retriable():
    spec = {
        "provider": "openai",
        "model": "m",
        "base_url": "http://127.0.0.1:9/v1",
        "api_key_env": None,
    }
    with pytest.raises(ProviderError) as info:
        complete(spec, Request(prompt="x"))
    assert info.value.retriable


# http ------------------------------------------------------------------------


def test_http_provider_templates_body_and_digs_output(fake_server):
    spec = {
        "provider": "http",
        "url": fake_server.url + "/app",
        "headers": {"x-app": "1"},
        "body": {"question": "{{prompt}}", "city": "{{vars.city}}"},
        "output_path": "data.answer",
    }
    _, response = complete(spec, Request(prompt="Eiffel Tower", vars={"city": "Paris"}))
    assert response.text.startswith("```json")
    assert fake_server.requests[0]["body"] == {"question": "Eiffel Tower", "city": "Paris"}
    assert fake_server.requests[0]["headers"]["x-app"] == "1"


def test_http_provider_serializes_non_string_output(fake_server):
    spec = {"provider": "http", "url": fake_server.url + "/app"}
    _, response = complete(spec, Request(prompt="x"))
    assert response.text == '{"data": {"answer": "I don\'t know."}}'


def test_dig():
    data = {"a": [{"b": 1}, {"b": 2}]}
    assert dig(data, "a.1.b") == 2
    assert dig(data, "a.-1.b") == 2
    with pytest.raises(ProviderError, match="stopped at 'c'"):
        dig(data, "a.0.c")


# command ---------------------------------------------------------------------


def test_command_stdin_and_env(tmp_path):
    script = tmp_path / "echo.py"
    script.write_text(
        "import os, sys\n"
        "print(sys.stdin.read().upper(), os.environ['EVALKIT_REPEAT'], os.environ['GREETING'])\n"
    )
    spec = {
        "provider": "command",
        "command": [sys.executable, "echo.py"],
        "env": {"GREETING": "hi"},
    }
    provider, response = complete(spec, Request(prompt="hello", repeat=2), base_dir=tmp_path)
    assert response.text == "HELLO 2 hi"
    assert provider.label.startswith("command:python")
    assert not provider.cache_by_default


def test_command_prompt_as_argument(tmp_path):
    spec = {
        "provider": "command",
        "command": [sys.executable, "-c", "import sys; print(sys.argv[1])", "{{prompt}}"],
    }
    _, response = complete(spec, Request(prompt="as arg"), base_dir=tmp_path)
    assert response.text == "as arg"


def test_command_failures(tmp_path):
    with pytest.raises(ProviderError, match="exited with status 3: oops"):
        complete(
            {
                "provider": "command",
                "command": [
                    sys.executable,
                    "-c",
                    "import sys; sys.stderr.write('oops'); sys.exit(3)",
                ],
            },
            Request(prompt="x"),
        )
    with pytest.raises(ProviderError, match="cannot start"):
        complete(
            {"provider": "command", "command": "definitely-not-a-program-xyz"}, Request(prompt="x")
        )
    with pytest.raises(ProviderError, match="timed out") as info:
        complete(
            {
                "provider": "command",
                "command": [sys.executable, "-c", "import time; time.sleep(5)"],
                "timeout": 0.2,
            },
            Request(prompt="x"),
        )
    assert info.value.retriable


def test_helpers():
    assert estimate_cost(None, 1, 1) is None
    assert is_retriable_status(429)
    assert is_retriable_status(500)
    assert not is_retriable_status(404)
