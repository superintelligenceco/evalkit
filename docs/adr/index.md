# Architecture decision records

Each record captures one decision that shapes evalkit, the context it was made in, and what it
costs. A record's status changes when a later decision replaces it.

| Record | Status |
| --- | --- |
| [0001. Suites are strict YAML files validated by pydantic](0001-strict-yaml-suites.md) | Accepted |
| [0002. Cache model responses in SQLite](0002-sqlite-response-cache.md) | Accepted |
| [0003. Release from a version tag, not release-please](0003-tag-driven-release.md) | Accepted |
| [0004. Ship standalone executables built with PyInstaller](0004-standalone-executables-with-pyinstaller.md) | Accepted |

To propose a new decision, copy the structure of an existing record into the next number and open
a pull request.
