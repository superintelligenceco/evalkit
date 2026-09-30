# 0001. Suites are strict YAML files validated by pydantic

Status: Accepted

## Context

Evals should live in the repository and change through code review, like tests. The people who
write them include product and support staff, not only Python developers. A suite format needs
to be readable in a diff, easy to write by hand, and hard to get silently wrong. A misspelled key
such as `fail_undr` that the loader ignores turns a gate off without anyone noticing.

## Decision

A suite is a YAML (or JSON) file. Tasks can also come from `.jsonl` datasets. evalkit validates the
file with pydantic models that set `extra="forbid"`, so every unknown key is an error with the file
path and the location of the problem. The same models generate the JSON Schema that
`evalkit schema` prints for editors. Custom logic goes in `python` graders, which the suite
references by `file.py:function`.

## Consequences

- Suites diff and review well, and typos fail loudly.
- Editors get completion and validation from the generated schema.
- A new option means a model change, a schema change, and a docs change, which keeps the three in
  step.
- Logic that doesn't fit a built-in grader needs a small Python file next to the suite.
