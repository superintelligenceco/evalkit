"""LLM-as-judge grading against a rubric."""

from __future__ import annotations

import re

from evalkit.config import LlmJudgeGrader
from evalkit.graders.base import Grade, GradeContext, GraderError, as_text, extract_json
from evalkit.providers.base import Request
from evalkit.templating import render

JUDGE_SYSTEM = (
    "You are a strict, consistent evaluator. You grade an AI system's output against a "
    "rubric and reply with JSON only."
)

JUDGE_TEMPLATE = """Grade the output against the rubric.

<rubric>
{rubric}
</rubric>

<input>
{input}
</input>
{reference}
<output>
{output}
</output>

Score the output from 1 (does not meet the rubric) to {scale} (fully meets it).
Reply with only a JSON object: {{"score": <integer 1-{scale}>, "reason": "<one sentence>"}}"""

_SCORE = re.compile(r"score\"?\s*[:=]\s*\"?(\d+(?:\.\d+)?)", re.IGNORECASE)


def build_judge_prompt(config: LlmJudgeGrader, ctx: GradeContext) -> str:
    rubric = render(config.rubric, ctx.template_vars) if "{{" in config.rubric else config.rubric
    reference = ""
    if ctx.task.expected is not None:
        reference = f"\n<reference>\n{as_text(ctx.task.expected)}\n</reference>\n"
    return JUDGE_TEMPLATE.format(
        rubric=rubric.strip(),
        input=ctx.prompt,
        reference=reference,
        output=ctx.output,
        scale=config.scale,
    )


def parse_judge_reply(text: str) -> tuple[float, str]:
    """Return ``(raw_score, reason)`` from a judge reply."""
    try:
        data = extract_json(text)
    except ValueError:
        data = None
    if isinstance(data, dict) and "score" in data:
        try:
            return float(data["score"]), str(data.get("reason", "")).strip()
        except (TypeError, ValueError):
            pass
    match = _SCORE.search(text)
    if match:
        return float(match.group(1)), ""
    raise ValueError("judge reply has no score")


async def grade_llm_judge(config: LlmJudgeGrader, ctx: GradeContext) -> Grade:
    if ctx.call_model is None:  # pragma: no cover - the runner always provides one
        raise GraderError("llm_judge: no model caller available")
    prompt = build_judge_prompt(config, ctx)
    response = await ctx.call_model(
        config.provider,
        Request(prompt=prompt, system=JUDGE_SYSTEM, seed=ctx.seed, repeat=ctx.repeat),
    )
    try:
        raw, reason = parse_judge_reply(response.text)
    except ValueError:
        return Grade("llm_judge", False, 0.0, f"unparseable judge reply: {response.text[:120]!r}")
    raw = max(1.0, min(float(config.scale), raw))
    minimum = config.min_score if config.min_score is not None else config.scale - 1
    score = (raw - 1) / (config.scale - 1)
    passed = raw >= minimum
    detail = f"{raw:g}/{config.scale}"
    return Grade(
        config.name or "llm_judge", passed, score, f"{detail}: {reason}" if reason else detail
    )
