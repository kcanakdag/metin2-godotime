#!/usr/bin/env python3
"""Run the isolated Godot editor lifecycle regression for MCP SceneCommands."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tools" / "fixtures" / "godot_scene_commands"
SOURCE_FILES = (
    ROOT / "client" / "project.godot",
    ROOT / "client" / "addons" / "godot_mcp" / "commands" / "scene_commands.gd",
)
ADDON_FILES = (
    "commands/scene_commands.gd",
    "commands/base_commands.gd",
    "utils/node_utils.gd",
    "utils/resource_utils.gd",
    "utils/type_parser.gd",
)


def sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def hash_or_missing(path: Path) -> str | None:
    return sha256(path) if path.is_file() else None


def processes_for(stage: Path) -> list[str]:
    output = subprocess.run(
        ["ps", "-eo", "args="], capture_output=True, check=True, text=True
    ).stdout.splitlines()
    return [line for line in output if str(stage) in line]


def copy_fixture(stage: Path) -> None:
    project = stage / "project"
    shutil.copytree(FIXTURE, project)
    addon_root = project / "addons" / "godot_mcp"
    for relative in ADDON_FILES:
        destination = addon_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "client" / "addons" / "godot_mcp" / relative, destination)


def report_path(data_root: Path) -> Path:
    matches = list(
        data_root.glob("godot/app_userdata/Mcp Scene Commands QA/scene-command-qa-report.json")
    )
    if len(matches) != 1:
        raise RuntimeError("the isolated editor did not create exactly one QA report")
    return matches[0]


def terminate_process_group(process: subprocess.Popen[str]) -> tuple[str, str]:
    """Stop the isolated editor and any child game it launched."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return process.communicate(timeout=5)


def process_is_running(pid: int) -> bool:
    status = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
    ).stdout.strip()
    return bool(status) and not status.startswith("Z")


def process_group_cleanup_self_test() -> int:
    """Exercise cleanup after a parent exits but a child retains its output pipe."""
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(child.pid, flush=True)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=0.2)
    except subprocess.TimeoutExpired:
        timed_out = True
        stdout, stderr = terminate_process_group(process)
    child_pid = int(stdout.strip()) if stdout.strip().isdigit() else None
    child_running = child_pid is not None and process_is_running(child_pid)
    result = {
        "child_pid": child_pid,
        "child_running": child_running,
        "parent_returncode": process.returncode,
        "stderr": stderr,
        "timed_out": timed_out,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if timed_out and child_pid is not None and not child_running else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default="godot", help="Godot 4.7 executable")
    parser.add_argument("--keep", action="store_true", help="keep the isolated project and logs")
    parser.add_argument(
        "--editor-timeout",
        type=float,
        default=45,
        help="seconds to wait before terminating the isolated editor process group",
    )
    parser.add_argument(
        "--self-test-process-group",
        action="store_true",
        help="exercise timeout cleanup with a disposable parent/child process group",
    )
    options = parser.parse_args()
    if not math.isfinite(options.editor_timeout) or options.editor_timeout <= 0:
        parser.error("--editor-timeout must be a positive finite number")
    if options.self_test_process_group:
        return process_group_cleanup_self_test()
    before = {str(path.relative_to(ROOT)): sha256(path) for path in SOURCE_FILES}
    stage = Path(tempfile.mkdtemp(prefix="godot-scene-commands-", dir=ROOT / ".local"))
    keep_stage = options.keep
    process: subprocess.Popen[str] | None = None
    log = stage / "editor.log"
    try:
        copy_fixture(stage)
        config = stage / "config"
        data = stage / "data"
        config.mkdir()
        data.mkdir()
        fixture_project = stage / "project" / "project.godot"
        fixture_project_before = sha256(fixture_project)
        settings_before = hash_or_missing(config / "godot" / "editor_settings-4.7.tres")
        environment = os.environ | {"XDG_CONFIG_HOME": str(config), "XDG_DATA_HOME": str(data)}
        command = [options.godot, "--headless", "--path", str(stage / "project"), "--editor"]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
            start_new_session=True,
        )
        editor_timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=options.editor_timeout)
        except subprocess.TimeoutExpired:
            editor_timed_out = True
            stdout, stderr = terminate_process_group(process)
        log.write_text(stdout + stderr)
        report: dict[str, object] | None = None
        report_error: str | None = None
        try:
            loaded_report = json.loads(report_path(data).read_text())
            if isinstance(loaded_report, dict):
                report = loaded_report
            else:
                report_error = "QA report must be a JSON object"
        except (OSError, RuntimeError, json.JSONDecodeError) as error:
            report_error = str(error)
        after = {str(path.relative_to(ROOT)): sha256(path) for path in SOURCE_FILES}
        fixture_project_after = sha256(fixture_project)
        report_is_valid = (
            report is not None
            and type(report.get("assertions")) is int
            and report["assertions"] > 0
            and isinstance(report.get("failures"), list)
        )
        failures = report.get("failures") if report is not None else None
        fixture_project_unchanged = fixture_project_before == fixture_project_after
        remaining_processes = processes_for(stage)
        failed = (
            editor_timed_out
            or process.returncode != 0
            or not report_is_valid
            or bool(failures)
            or before != after
            or not fixture_project_unchanged
            or bool(remaining_processes)
        )
        keep_stage = keep_stage or failed
        result = {
            "assertions": report.get("assertions") if report is not None else None,
            "child_args": report.get("child_args") if report is not None else None,
            "editor_returncode": process.returncode,
            "editor_timed_out": editor_timed_out,
            "failures": failures,
            "source_hashes_before": before,
            "source_hashes_after": after,
            "source_unchanged": before == after,
            "fixture_project_hash_before": fixture_project_before,
            "fixture_project_hash_after": fixture_project_after,
            "fixture_project_unchanged": fixture_project_unchanged,
            "editor_settings_hash_before": settings_before,
            "editor_settings_hash_after": hash_or_missing(
                config / "godot" / "editor_settings-4.7.tres"
            ),
            "remaining_stage_processes": remaining_processes,
            "report_error": report_error,
            "report_is_valid": report_is_valid,
            "stage_retained": keep_stage,
            "log": str(log),
            "stage": str(stage),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if failed else 0
    except BaseException as error:
        keep_stage = True
        if process is not None:
            stdout, stderr = terminate_process_group(process)
            log.write_text(stdout + stderr)
        else:
            (stage / "runner-error.log").write_text(str(error))
        raise
    finally:
        if not keep_stage:
            shutil.rmtree(stage)


if __name__ == "__main__":
    raise SystemExit(main())
