"""Build a standalone ``evalkit`` executable with PyInstaller and smoke-test it.

Usage: python scripts/build_binary.py ASSET_NAME

Run it from the repository root in an environment where evalkit and PyInstaller are installed.
It writes ``dist/ASSET_NAME`` (``ASSET_NAME.exe`` on Windows), then runs ``evalkit init`` and
``evalkit run`` with the new executable in an empty temporary directory. The starter suite uses
the offline ``mock`` provider, so the smoke test needs no network or API key.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build(name: str) -> Path:
    work = ROOT / "build" / "pyinstaller"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--onefile",
            "--clean",
            "--noconfirm",
            "--name",
            name,
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(work),
            "--specpath",
            str(work),
            # evalkit reads its version from the installed package metadata.
            "--copy-metadata",
            "sic-evalkit",
            "--collect-data",
            "jsonschema_specifications",
            str(ROOT / "src" / "evalkit" / "__main__.py"),
        ],
        check=True,
    )
    exe = ROOT / "dist" / (name + (".exe" if os.name == "nt" else ""))
    if not exe.is_file():
        raise SystemExit(f"PyInstaller did not produce {exe}")
    return exe


def smoke_test(exe: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
        for args in (["--version"], ["init"], ["run", "evals.yaml"]):
            print(f"$ {exe.name} {' '.join(args)}", flush=True)
            subprocess.run([str(exe), *args], cwd=tmp, env=env, check=True)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    exe = build(sys.argv[1])
    smoke_test(exe)
    print(f"built {exe.relative_to(ROOT)} ({exe.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
