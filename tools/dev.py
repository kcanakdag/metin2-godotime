#!/usr/bin/env python3
"""Install or run this repository's development checks without global Python installs."""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = ROOT / ".local/venv-dev"
BIN = ENVIRONMENT / ("Scripts" if os.name == "nt" else "bin")
GROUPS = ("python", "gdscript", "rust", "typescript")


def environment_tool(name: str) -> str:
    suffix = ".exe" if os.name == "nt" else ""
    path = BIN / (name + suffix)
    if not path.is_file():
        raise FileNotFoundError("Run `python3 tools/dev.py setup` to install project linters.")
    return str(path)


def system_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise FileNotFoundError(f"Required tool missing from PATH: {name}")
    return path


def run(command: list[str]) -> int:
    print("+ " + shlex.join(command), flush=True)
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def setup() -> int:
    if sys.version_info < (3, 12):
        raise RuntimeError("Project tools require Python 3.12 or newer.")
    if not (ENVIRONMENT / "pyvenv.cfg").is_file():
        venv.EnvBuilder(with_pip=True).create(ENVIRONMENT)
    return run(
        [
            environment_tool("python"),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--cache-dir",
            str(ROOT / ".cache/pip"),
            "-r",
            "tools/requirements-dev.txt",
        ]
    )


def owned_sources(suffix: str, roots: tuple[str, ...]) -> list[str]:
    excluded = {"addons", "spacetime_bindings", "node_modules", "build", "target", "__pycache__"}
    return sorted(
        str(path.relative_to(ROOT))
        for source_root in roots
        for path in (ROOT / source_root).rglob("*" + suffix)
        if not any(
            part in excluded or part.startswith(".") for part in path.relative_to(ROOT).parts
        )
    )


def commands(group: str, format_code: bool) -> list[list[str]]:
    if group == "python":
        files = owned_sources(".py", ("tools", "tests"))
        if not files:
            raise RuntimeError("No owned Python sources found.")
        ruff = environment_tool("ruff")
        return [
            [ruff, "check", *(["--fix"] if format_code else []), *files],
            [ruff, "format", *([] if format_code else ["--check"]), *files],
        ]
    if group == "gdscript":
        files = owned_sources(".gd", ("client", "tools"))
        if not files:
            raise RuntimeError("No owned GDScript sources found.")
        launcher = [environment_tool("python"), "tools/gdtoolkit_local.py"]
        return [
            [*launcher, "format", *([] if format_code else ["--check"]), *files],
            *([] if format_code else [[*launcher, "lint", *files]]),
        ]
    if group == "rust":
        cargo = system_tool("cargo")
        manifest = ["--manifest-path", "server/Cargo.toml"]
        return [
            [cargo, "fmt", *manifest, *([] if format_code else ["--", "--check"])],
            *(
                []
                if format_code
                else [
                    [
                        cargo,
                        "clippy",
                        *manifest,
                        "--locked",
                        "--all-targets",
                        "--all-features",
                        "--",
                        "-D",
                        "warnings",
                    ]
                ]
            ),
        ]
    if group == "typescript":
        if format_code:
            return []
        checks = []
        for directory, setup_command in (
            ("tools/godot-mcp-server", "make mcp-build"),
            ("auth", "make auth-setup"),
        ):
            compiler = ROOT / directory / "node_modules/typescript/bin/tsc"
            if not compiler.is_file():
                raise FileNotFoundError(
                    f"Run `{setup_command}` to install the locked {directory} dependencies."
                )
            checks.append(
                [
                    system_tool("node"),
                    str(compiler),
                    "--project",
                    directory + "/tsconfig.json",
                    "--noEmit",
                ]
            )
        return checks
    raise ValueError(group)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "lint", "format"))
    parser.add_argument("--only", choices=GROUPS)
    options = parser.parse_args()
    if options.action == "setup":
        if options.only:
            parser.error("--only applies to lint or format, not setup")
        return setup()
    failures = []
    for group in (options.only,) if options.only else GROUPS:
        try:
            failed = False
            for command in commands(group, options.action == "format"):
                if run(command) != 0:
                    failed = True
            if failed:
                failures.append(group)
        except (FileNotFoundError, RuntimeError) as error:
            print(f"{group}: {error}", file=sys.stderr)
            failures.append(group)
    if failures:
        print("Failed checks: " + ", ".join(failures), file=sys.stderr)
        return 1
    print("Development checks completed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
