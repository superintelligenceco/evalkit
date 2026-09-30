"""Runs a suite: renders prompts, calls the target, grades outputs."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from evalkit.cache import ResponseCache, cache_key
from evalkit.config import ProviderConfig, Suite, Task
from evalkit.graders import GradeContext, GraderError, run_grader, task_context
from evalkit.providers import Provider, ProviderError, Request, Response, build_provider
from evalkit.results import RunRecord, SuiteResult, TaskResult
from evalkit.templating import TemplateError, render

ProgressCallback = Callable[[TaskResult, RunRecord], None]


def render_prompt(suite: Suite, task: Task) -> str:
    if suite.prompt is None:
        assert isinstance(task.input, str)  # guaranteed by Suite validation
        return task.input
    return render(suite.prompt, task_context(task))


def select_tasks(
    tasks: Sequence[Task],
    *,
    tags: Sequence[str] = (),
    match: str | None = None,
    limit: int | None = None,
) -> list[Task]:
    selected = [
        task
        for task in tasks
        if (not tags or set(tags) & set(task.tags)) and (match is None or match in (task.id or ""))
    ]
    return selected[:limit] if limit is not None else selected


class Runner:
    """Executes a :class:`Suite` with bounded concurrency, retries, and caching."""

    def __init__(
        self,
        suite: Suite,
        *,
        use_cache: bool | None = None,
        cache_path: str | Path | None = None,
        concurrency: int | None = None,
        repeat: int | None = None,
        seed: int | None = None,
        tasks: Sequence[Task] | None = None,
        progress: ProgressCallback | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.suite = suite
        settings = suite.settings
        self.concurrency = concurrency or settings.concurrency
        self.repeat = repeat or settings.repeat
        self.seed = settings.seed if seed is None else seed
        self.tasks = list(tasks) if tasks is not None else list(suite.tasks)
        self.progress = progress
        self.cache_enabled = settings.cache if use_cache is None else use_cache
        self.cache_path = Path(cache_path or settings.cache_path)
        self._client = client
        self._providers: dict[int, tuple[Provider, bool]] = {}
        self.cache: ResponseCache | None = None

    def _provider(self, config: ProviderConfig, client: httpx.AsyncClient) -> tuple[Provider, bool]:
        entry = self._providers.get(id(config))
        if entry is None:
            provider = build_provider(config, base_dir=self.suite.base_dir, client=client)
            wants_cache = provider.cache_by_default if config.cache is None else config.cache
            entry = (provider, self.cache_enabled and wants_cache)
            self._providers[id(config)] = entry
        return entry

    async def _call(
        self, provider: Provider, use_cache: bool, request: Request
    ) -> tuple[Response, int]:
        key = (
            cache_key({"label": provider.label, **provider.identity()}, request)
            if use_cache
            else ""
        )
        if use_cache and self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                return hit, 0
        settings = self.suite.settings
        attempt = 0
        while True:
            attempt += 1
            started = time.perf_counter()
            try:
                response = await provider.complete(request)
            except ProviderError as exc:
                if not exc.retriable or attempt > settings.retries:
                    raise ProviderError(
                        f"{exc} (after {attempt} attempt{'s' if attempt > 1 else ''})",
                        retriable=exc.retriable,
                    ) from exc
                await asyncio.sleep(settings.retry_backoff * 2 ** (attempt - 1))
                continue
            response.latency_ms = (time.perf_counter() - started) * 1000
            if use_cache and self.cache is not None:
                self.cache.put(key, provider.label, response)
            return response, attempt

    async def _run_one(
        self,
        task: Task,
        prompt: str,
        repeat_index: int,
        target: tuple[Provider, bool],
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
    ) -> RunRecord:
        request = Request(
            prompt=prompt,
            system=self.suite.system,
            seed=self.seed,
            repeat=repeat_index,
            vars=task_context(task),
        )

        async def call_model(config: ProviderConfig | None, judge_request: Request) -> Response:
            judge_config = config or self.suite.judge
            if judge_config is None:  # pragma: no cover - rejected at load time
                raise GraderError("llm_judge: no judge provider configured")
            provider, use_cache = self._provider(judge_config, client)
            response, _ = await self._call(provider, use_cache, judge_request)
            return response

        async with semaphore:
            try:
                response, attempts = await self._call(target[0], target[1], request)
            except ProviderError as exc:
                return RunRecord(repeat=repeat_index, output="", error=str(exc))
            record = RunRecord(
                repeat=repeat_index,
                output=response.text,
                latency_ms=response.latency_ms,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=response.cost_usd,
                cached=response.cached,
                attempts=max(attempts, 1),
            )
            ctx = GradeContext(
                output=response.text,
                task=task,
                prompt=prompt,
                base_dir=self.suite.base_dir,
                call_model=call_model,
                seed=self.seed,
                repeat=repeat_index,
            )
            for grader in self.suite.graders_for(task):
                try:
                    record.grades.append(await run_grader(grader, ctx))
                except (GraderError, TemplateError, ProviderError) as exc:
                    record.error = f"grader {grader.name or grader.type}: {exc}"
                    break
            return record

    async def run(self) -> SuiteResult:
        started_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        started = time.perf_counter()
        if self.cache_enabled:
            self.cache = ResponseCache(self.cache_path)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient()
        semaphore = asyncio.Semaphore(self.concurrency)
        try:
            target = self._provider(self.suite.target, client)
            results: list[TaskResult] = []
            jobs: list[asyncio.Task[None]] = []

            for task in self.tasks:
                assert task.id is not None
                try:
                    prompt = render_prompt(self.suite, task)
                except TemplateError as exc:
                    result = TaskResult(
                        id=task.id, prompt="", expected=task.expected, tags=task.tags
                    )
                    result.runs = [
                        RunRecord(repeat=i, output="", error=f"prompt: {exc}")
                        for i in range(self.repeat)
                    ]
                    results.append(result)
                    continue
                result = TaskResult(
                    id=task.id,
                    prompt=prompt,
                    expected=task.expected,
                    tags=task.tags,
                    required_pass_rate=self.suite.settings.task_pass_rate,
                )
                results.append(result)
                for index in range(self.repeat):
                    jobs.append(
                        asyncio.create_task(
                            self._collect(result, task, prompt, index, target, client, semaphore)
                        )
                    )
            await asyncio.gather(*jobs)
            for result in results:
                result.runs.sort(key=lambda run: run.repeat)
        finally:
            for provider, _ in self._providers.values():
                await provider.aclose()
            if owns_client:
                await client.aclose()
            if self.cache is not None:
                self.cache.close()

        return SuiteResult(
            suite=self.suite.name,
            description=self.suite.description,
            target=target[0].label,
            started_at=started_at,
            duration_s=time.perf_counter() - started,
            repeat=self.repeat,
            seed=self.seed,
            tasks=results,
            fail_under=self.suite.settings.fail_under,
        )

    async def _collect(
        self,
        result: TaskResult,
        task: Task,
        prompt: str,
        index: int,
        target: tuple[Provider, bool],
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
    ) -> None:
        record = await self._run_one(task, prompt, index, target, client, semaphore)
        result.runs.append(record)
        if self.progress is not None:
            self.progress(result, record)


def run_suite(suite: Suite, **kwargs: object) -> SuiteResult:
    """Synchronous convenience wrapper around :meth:`Runner.run`."""
    return asyncio.run(Runner(suite, **kwargs).run())  # type: ignore[arg-type]
