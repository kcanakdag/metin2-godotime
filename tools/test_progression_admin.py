#!/usr/bin/env python3
"""Run the two-phase authenticated progression-admin smoke on a disposable P2 database."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from progression_operator import AuthSession, OperatorError, http_origin, private_json

ROOT = Path(__file__).resolve().parents[1]


def create_account(origin: str, label: str) -> tuple[dict[str, str], AuthSession, str]:
    auth = AuthSession(origin)
    username = f"p2_admin_{label}_{uuid.uuid4().hex[:10]}"
    password = secrets.token_urlsafe(32)
    auth.secrets.extend((username, password))
    _, auth.session = auth.request(
        "/auth/sign-up/email",
        {
            "username": username,
            "name": username,
            "email": username + "@example.invalid",
            "password": password,
        },
    )
    if not auth.session:
        raise OperatorError("Fixture account creation did not return a session.")
    value, replacement = auth.request("/auth/token", bearer=auth.session)
    if replacement:
        auth.session = replacement
    if not isinstance(value, dict) or not isinstance(value.get("token"), str):
        raise OperatorError("Fixture account creation did not return a game credential.")
    token = value["token"]
    auth.secrets.append(token)
    return {"username": username, "password": password}, auth, token


def sign_in(origin: str, saved: dict[str, object]) -> tuple[AuthSession, str]:
    username = saved.get("username")
    password = saved.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        raise OperatorError("Private fixture account credentials are invalid.")
    auth = AuthSession(origin)
    return auth, auth.sign_in(username, password)


def stage_project(stage: Path) -> None:
    for directory in ("addons/SpacetimeDB", "spacetime_bindings"):
        shutil.copytree(ROOT / "client" / directory, stage / directory)
    for source, destination in (
        (ROOT / "client/scripts/net/game_connection.gd", stage / "scripts/net/game_connection.gd"),
        (ROOT / "tools/progression_admin_smoke.gd", stage / "tests/progression_admin_smoke.gd"),
        (ROOT / "tools/skill_reaction_smoke.gd", stage / "tests/skill_reaction_smoke.gd"),
        (ROOT / "tools/skill_batch_smoke.gd", stage / "tests/skill_batch_smoke.gd"),
        (ROOT / "tools/charge_smoke.gd", stage / "tests/charge_smoke.gd"),
        (ROOT / "tools/charge_strike_smoke.gd", stage / "tests/charge_strike_smoke.gd"),
        (ROOT / "tools/crush_smoke.gd", stage / "tests/crush_smoke.gd"),
        (ROOT / "tools/crush_death_smoke.gd", stage / "tests/crush_death_smoke.gd"),
        (ROOT / "tools/crush_overlap_smoke.gd", stage / "tests/crush_overlap_smoke.gd"),
    ):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (stage / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="MT2 P2 Admin Smoke"\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
    )


def run_godot(
    godot: str,
    stage: Path,
    config: dict[str, object],
    auths: list[AuthSession],
    log_path: Path,
) -> dict[str, object]:
    config_path = stage / "admin-smoke-config.json"
    descriptor = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(config, handle)
    environment = os.environ.copy()
    environment["XDG_DATA_HOME"] = str(stage / ".data")
    environment["XDG_CONFIG_HOME"] = str(stage / ".config")
    import_process = subprocess.run(
        [godot, "--headless", "--path", str(stage), "--editor", "--import", "--quit"],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    if import_process.returncode:
        log_path.write_text(import_process.stdout)
        raise OperatorError(f"Admin smoke project import failed; log: {log_path}")
    script = {
        "skill_reactions": "skill_reaction_smoke.gd",
        "skill_batch": "skill_batch_smoke.gd",
        "charge": "charge_smoke.gd",
        "charge_strike": "charge_strike_smoke.gd",
        "crush": "crush_smoke.gd",
        "crush_death": "crush_death_smoke.gd",
        "crush_overlap": "crush_overlap_smoke.gd",
    }.get(str(config["mode"]), "progression_admin_smoke.gd")
    command = [
        godot,
        "--headless",
        "--path",
        str(stage),
        "--script",
        "res://tests/" + script,
        "--",
        "--admin-smoke-config",
        str(config_path),
    ]
    try:
        process = subprocess.run(
            command,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        for auth in auths:
            output = auth.redact(output)
        log_path.write_text(output)
        raise OperatorError(f"Admin smoke timed out; sanitized log: {log_path}") from None
    output = process.stdout
    for auth in auths:
        output = auth.redact(output)
    log_path.write_text(output)
    result_path = stage / "admin-smoke-result.json"
    if result_path.is_file():
        retained = result_path.read_text()
        for auth in auths:
            retained = auth.redact(retained)
        log_path.with_suffix(".result.json").write_text(retained)
    if process.returncode or not result_path.is_file():
        raise OperatorError(f"Admin smoke failed; sanitized log: {log_path}")
    result = json.loads(result_path.read_text())
    if not isinstance(result, dict) or result.get("passed") is not True:
        raise OperatorError(f"Admin smoke checks failed; sanitized log: {log_path}")
    return result


def write_private(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OperatorError("Refusing to replace a symlinked private fixture.")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


def write_private_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OperatorError("Refusing to replace a symlinked private fixture.")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(value)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=(
            "prepare",
            "verify",
            "skills",
            "skill_combat",
            "training_dummy",
            "three_way_cut",
            "skill_reactions",
            "skill_batch",
            "charge",
            "charge_strike",
            "crush",
            "crush_death",
            "crush_overlap",
        ),
    )
    parser.add_argument("--server", default="http://127.0.0.1:8186")
    parser.add_argument("--game-server", default="http://127.0.0.1:13223")
    parser.add_argument("--database", required=True)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--reaction-skill",
        type=int,
        choices=(1, 16, 17),
        default=None,
        help="Skill qualified by skill_reactions (default: Three-Way Cut, 1)",
    )
    options = parser.parse_args()
    if options.reaction_skill is not None and options.phase != "skill_reactions":
        parser.error("--reaction-skill requires the skill_reactions phase")
    return options


def main() -> None:
    options = arguments()
    origin = http_origin(options.server)
    game_server = http_origin(options.game_server)
    if not options.database.startswith("mt2-p2-"):
        raise OperatorError("Admin smoke requires a disposable database named with mt2-p2-.")
    fixture_path = options.fixture.resolve()
    report_path = options.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    auths: list[AuthSession] = []
    try:
        if options.phase == "prepare":
            if fixture_path.is_file():
                saved = private_json(fixture_path, "admin smoke fixture")
                accounts = saved.get("accounts")
                if not isinstance(accounts, list) or len(accounts) != 2:
                    raise OperatorError("Admin smoke fixture requires exactly two accounts.")
                first_auth, first_token = sign_in(origin, accounts[0])
                second_auth, second_token = sign_in(origin, accounts[1])
                auths = [first_auth, second_auth]
            else:
                first, first_auth, first_token = create_account(origin, "a")
                second, second_auth, second_token = create_account(origin, "b")
                auths = [first_auth, second_auth]
                saved = {"accounts": [first, second]}
                write_private(fixture_path, saved)
            mode = "prepare"
        else:
            saved = private_json(fixture_path, "admin smoke fixture")
            accounts = saved.get("accounts")
            if not isinstance(accounts, list) or len(accounts) != 2:
                raise OperatorError("Admin smoke fixture requires exactly two accounts.")
            first_auth, first_token = sign_in(origin, accounts[0])
            second_auth, second_token = sign_in(origin, accounts[1])
            auths = [first_auth, second_auth]
            mode = options.phase

        (ROOT / ".local").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="progression-admin-", dir=ROOT / ".local") as raw:
            stage = Path(raw)
            stage_project(stage)
            result = run_godot(
                options.godot,
                stage,
                {
                    "mode": mode,
                    "reaction_skill": options.reaction_skill or 1,
                    "server": game_server,
                    "database": options.database,
                    "tokens": [first_token, second_token],
                    "report": str(stage / "admin-smoke-result.json"),
                },
                auths,
                report_path.with_suffix(".log"),
            )
        if options.phase == "prepare":
            saved["account_identities"] = result["account_identities"]
            saved["database"] = options.database
            saved["server"] = origin
            saved["game_server"] = game_server
            accounts = saved["accounts"]
            credential_path = fixture_path.with_suffix(".operator-credentials.json")
            reason_path = fixture_path.with_suffix(".operator-reason.txt")
            write_private(credential_path, accounts[0])
            write_private_text(reason_path, "P2 structured operator CLI QA\n")
            saved["operator_credential_file"] = str(credential_path)
            saved["operator_reason_file"] = str(reason_path)
            write_private(fixture_path, saved)
        report_path.write_text(json.dumps(result, indent=2) + "\n")
        print(
            f"P2 progression admin {options.phase}: {len(result['checks'])} checks passed; "
            f"report: {report_path}"
        )
        if options.phase == "prepare":
            print(f"Bootstrap account identity: {result['account_identities'][0]}")
    finally:
        first_token = ""
        second_token = ""
        for auth in auths:
            auth.close()


if __name__ == "__main__":
    try:
        main()
    except (OperatorError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
