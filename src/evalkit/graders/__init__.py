"""Graders decide whether an output passes."""

from __future__ import annotations

from evalkit.config import (
    ContainsGrader,
    ExactGrader,
    GraderConfig,
    JsonSchemaGrader,
    LlmJudgeGrader,
    NumericGrader,
    PythonGrader,
    RegexGrader,
)
from evalkit.graders.base import Grade, GradeContext, GraderError, extract_json, task_context
from evalkit.graders.builtin import (
    grade_contains,
    grade_exact,
    grade_json_schema,
    grade_numeric,
    grade_python,
    grade_regex,
)
from evalkit.graders.judge import grade_llm_judge

__all__ = ["Grade", "GradeContext", "GraderError", "extract_json", "run_grader", "task_context"]


async def _dispatch(config: GraderConfig, ctx: GradeContext) -> Grade:
    if isinstance(config, ExactGrader):
        return grade_exact(config, ctx)
    if isinstance(config, ContainsGrader):
        return grade_contains(config, ctx)
    if isinstance(config, RegexGrader):
        return grade_regex(config, ctx)
    if isinstance(config, JsonSchemaGrader):
        return grade_json_schema(config, ctx)
    if isinstance(config, NumericGrader):
        return grade_numeric(config, ctx)
    if isinstance(config, PythonGrader):
        return await grade_python(config, ctx)
    if isinstance(config, LlmJudgeGrader):
        return await grade_llm_judge(config, ctx)
    raise TypeError(f"unsupported grader: {type(config).__name__}")  # pragma: no cover


async def run_grader(config: GraderConfig, ctx: GradeContext) -> Grade:
    """Run one grader, applying ``name``, ``negate``, and ``weight``."""
    grade = await _dispatch(config, ctx)
    if config.negate:
        grade = Grade(
            grade.grader,
            not grade.passed,
            1.0 - grade.score,
            f"negated: {grade.reason}" if grade.reason else "negated",
        )
        grade.grader = f"not {grade.grader}"
    if config.name:
        grade.grader = config.name
    grade.weight = config.weight
    return grade
