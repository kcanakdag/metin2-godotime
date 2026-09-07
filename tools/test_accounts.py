#!/usr/bin/env python3
"""Exercise two fresh accounts through real HTTP auth and Godot subscriptions."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


class AuthClient:
    """Keep fixture credentials in memory and remove them from subprocess output."""

    def __init__(self, server: str) -> None:
        origin = urllib.parse.urlsplit(server)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.hostname
            or origin.username
            or origin.password
            or origin.path not in {"", "/"}
            or origin.query
            or origin.fragment
        ):
            raise RuntimeError("--server must be an HTTP(S) origin with the /auth proxy.")
        self.server = server.rstrip("/")
        self.secrets: list[str] = []
        self.sessions: list[str] = []

    def redact(self, value: str | bytes | None) -> str:
        text = value.decode(errors="replace") if isinstance(value, bytes) else value or ""
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, "[credential redacted]")
        return JWT_PATTERN.sub("[JWT redacted]", text)

    def request(self, path: str, body: dict | None = None, session: str = "") -> tuple[object, str]:
        headers = {"Accept": "application/json", "Origin": self.server}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if session:
            headers["Authorization"] = "Bearer " + session
        request = urllib.request.Request(self.server + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                value = json.load(response)
                signed_session = response.headers.get("set-auth-token", "")
        except urllib.error.HTTPError as error:
            retry = error.headers.get("Retry-After") or error.headers.get("X-Retry-After")
            suffix = f"; retry after {retry} seconds" if retry and retry.isdigit() else ""
            raise RuntimeError(f"Auth {path} returned HTTP {error.code}{suffix}.") from None
        except (OSError, ValueError) as error:
            raise RuntimeError(f"Auth {path} failed ({type(error).__name__}).") from None
        if signed_session:
            self.secrets.append(signed_session)
        if isinstance(value, dict) and isinstance(value.get("token"), str):
            self.secrets.append(value["token"])
        return value, signed_session

    def create_account(self, username: str) -> str:
        password = secrets.token_urlsafe(32)
        self.secrets.append(password)
        _, session = self.request(
            "/auth/sign-up/email",
            {
                "username": username,
                "name": username,
                "email": username + "@example.invalid",
                "password": password,
            },
        )
        if not session:
            raise RuntimeError("Sign-up omitted its signed set-auth-token response header.")
        self.sessions.append(session)
        value, replacement = self.request("/auth/token", session=session)
        if replacement:
            self.sessions[-1] = replacement
        if not isinstance(value, dict) or not isinstance(value.get("token"), str):
            raise RuntimeError("Auth /auth/token omitted the game credential.")
        token = value["token"]
        if not JWT_PATTERN.fullmatch(token):
            raise RuntimeError("Auth /auth/token returned an invalid game credential format.")
        return token

    def game_token(self, session_index: int) -> str:
        value, replacement = self.request("/auth/token", session=self.sessions[session_index])
        if replacement:
            self.sessions[session_index] = replacement
        if not isinstance(value, dict) or not isinstance(value.get("token"), str):
            raise RuntimeError("Auth /auth/token omitted the renewed game credential.")
        token = value["token"]
        if not JWT_PATTERN.fullmatch(token):
            raise RuntimeError("Auth /auth/token returned an invalid renewed credential format.")
        self.secrets.append(token)
        return token

    def logout(self) -> bool:
        successful = True
        for session in self.sessions:
            try:
                self.request("/auth/sign-out", {}, session)
            except RuntimeError:
                successful = False
        self.sessions.clear()
        return successful


def stage_project(stage: Path) -> None:
    for directory in ("addons/SpacetimeDB", "spacetime_bindings"):
        shutil.copytree(ROOT / "client" / directory, stage / directory)
    for filename in (
        "scripts/net/game_connection.gd",
        "tests/account_smoke.gd",
        "tests/multiplayer_smoke.gd",
        "tests/progression_combat_smoke.gd",
        "tests/progression_shared_smoke.gd",
    ):
        destination = stage / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "client" / filename, destination)
    (stage / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="MT2 Account Tests"\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
    )


def run_godot(
    godot: str, stage: Path, auth: AuthClient, log: Path, *arguments: str, timeout: int = 120
) -> str:
    environment = os.environ.copy()
    environment["XDG_DATA_HOME"] = str(stage / ".data")
    environment["XDG_CONFIG_HOME"] = str(stage / ".config")
    command = [godot, "--headless", "--path", str(stage), *arguments]
    try:
        result = subprocess.run(
            command,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        log.write_text(auth.redact(error.stdout))
        raise RuntimeError(
            f"Godot timed out after {timeout} seconds; sanitized log: {log}"
        ) from None
    output = auth.redact(result.stdout)
    log.write_text(output)
    if result.returncode or "SCRIPT ERROR:" in output or "\nERROR:" in output:
        raise RuntimeError(f"Godot account check failed; sanitized log: {log}")
    return output


def merge_subreport(report: dict, subreport: Path, prefix: str, report_path: Path) -> None:
    """Persist completed checks even when a later progression process fails."""
    if not subreport.is_file():
        return
    result = json.loads(subreport.read_text())
    report["checks"].extend(
        {
            "name": f"{prefix}_{check['name']}",
            "passed": check["passed"],
        }
        for check in result.get("checks", [])
    )
    report["passed"] = bool(report["checks"]) and all(check["passed"] for check in report["checks"])
    report_path.write_text(json.dumps(report, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:3210")
    parser.add_argument(
        "--game-server",
        help="Optional direct game origin when auth and the disposable database use different routes.",
    )
    parser.add_argument("--database", default="mt2-yongan-v2")
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--report", type=Path, default=ROOT / ".local/accounts-report.json")
    parser.add_argument(
        "--progression",
        action="store_true",
        help="Continue ordinary authenticated Wild Dog kills through level 2.",
    )
    options = parser.parse_args()
    report_path = options.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / ".local").mkdir(exist_ok=True)
    auth = AuthClient(options.server)
    report_path.write_text(
        json.dumps({"passed": False, "database": options.database, "checks": []}, indent=2) + "\n"
    )
    health, _ = auth.request("/auth/health")
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise RuntimeError("The selected origin does not expose a healthy /auth service.")
    game_server = (options.game_server or auth.server).rstrip("/")
    schema_url = (
        f"{game_server}/v1/database/"
        f"{urllib.parse.quote(options.database, safe='')}/schema?version=10"
    )
    try:
        with urllib.request.urlopen(schema_url, timeout=15) as response:
            schema = json.load(response)
    except (OSError, ValueError, urllib.error.HTTPError) as error:
        raise RuntimeError(
            f"The selected game route does not expose the requested database schema "
            f"({type(error).__name__})."
        ) from None
    if not isinstance(schema, dict):
        raise RuntimeError("The selected game route returned an invalid database schema.")
    try:
        with tempfile.TemporaryDirectory(prefix="accounts-", dir=ROOT / ".local") as scratch:
            stage = Path(scratch)
            stage_project(stage)
            run_godot(
                options.godot,
                stage,
                auth,
                report_path.with_suffix(".import.log"),
                "--editor",
                "--import",
                "--quit",
                "--lsp-port",
                "6165",
                "--dap-port",
                "6166",
            )
            scripts = [
                ("spacetime_bindings/schema/module_game_client.gd", "bindings"),
                ("tests/account_smoke.gd", "smoke"),
            ]
            if options.progression:
                scripts.append(("tests/progression_combat_smoke.gd", "progression"))
                scripts.append(("tests/progression_shared_smoke.gd", "shared"))
            for script, label in scripts:
                run_godot(
                    options.godot,
                    stage,
                    auth,
                    report_path.with_suffix(f".{label}-parse.log"),
                    "--check-only",
                    "--script",
                    "res://" + script,
                )
            suffix = uuid.uuid4().hex[:12]
            tokens = [auth.create_account(f"acct_{suffix}_{index}") for index in range(2)]
            definitions = json.loads(
                (ROOT / "server/content/p0-warrior-dog/actions.v1.json").read_text()
            )
            definition_hash = definitions.get("gameplay_definition_hash")
            if not isinstance(definition_hash, str) or not re.fullmatch(
                r"[0-9a-f]{64}", definition_hash
            ):
                raise RuntimeError("Trusted server definitions have no valid gameplay hash.")
            print(
                "Created two fresh accounts through HTTP; checking real Godot subscriptions.",
                flush=True,
            )
            fixture = stage / "account-config.json"
            private_report = stage / "account-report.json"
            descriptor = os.open(fixture, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as handle:
                json.dump(
                    {
                        "server": game_server,
                        "database": options.database,
                        "tokens": tokens,
                        "definition_hash": definition_hash,
                        "report": str(private_report),
                    },
                    handle,
                )
            try:
                output = run_godot(
                    options.godot,
                    stage,
                    auth,
                    report_path.with_suffix(".log"),
                    "--script",
                    "res://tests/account_smoke.gd",
                    "--",
                    "--account-config",
                    str(fixture),
                    timeout=240,
                )
            finally:
                if private_report.is_file():
                    report_path.write_text(auth.redact(private_report.read_text()))
            if not private_report.is_file():
                raise RuntimeError("Godot did not produce its account report.")
            report = json.loads(report_path.read_text())
            if not report.get("passed") or "MT2_MULTIPLAYER_SMOKE PASS" not in output:
                raise RuntimeError(f"Godot account checks failed; report: {report_path}")
            if options.progression:
                shared_report = stage / "progression-shared.json"
                with fixture.open("w") as handle:
                    json.dump(
                        {
                            "server": game_server,
                            "database": options.database,
                            "tokens": [auth.game_token(0), auth.game_token(1)],
                            "report": str(shared_report),
                        },
                        handle,
                    )
                try:
                    shared_output = run_godot(
                        options.godot,
                        stage,
                        auth,
                        report_path.with_suffix(".progression-shared.log"),
                        "--script",
                        "res://tests/progression_shared_smoke.gd",
                        "--",
                        "--progression-config",
                        str(fixture),
                        timeout=90,
                    )
                finally:
                    merge_subreport(report, shared_report, "progression_shared", report_path)
                shared = json.loads(shared_report.read_text())
                if not shared.get("passed") or "MT2_MULTIPLAYER_SMOKE PASS" not in shared_output:
                    raise RuntimeError(f"Godot shared progression failed; report: {shared_report}")
                for target_kills in (5, 10, 15, 20):
                    segment_report = stage / f"progression-{target_kills}.json"
                    with fixture.open("w") as handle:
                        json.dump(
                            {
                                "server": game_server,
                                "database": options.database,
                                "token": auth.game_token(0),
                                "target_kills": target_kills,
                                "report": str(segment_report),
                            },
                            handle,
                        )
                    try:
                        segment_output = run_godot(
                            options.godot,
                            stage,
                            auth,
                            report_path.with_suffix(f".progression-{target_kills}.log"),
                            "--script",
                            "res://tests/progression_combat_smoke.gd",
                            "--",
                            "--progression-config",
                            str(fixture),
                            timeout=120,
                        )
                    finally:
                        merge_subreport(
                            report,
                            segment_report,
                            f"progression_{target_kills}",
                            report_path,
                        )
                    segment = json.loads(segment_report.read_text())
                    if (
                        not segment.get("passed")
                        or "MT2_MULTIPLAYER_SMOKE PASS" not in segment_output
                    ):
                        raise RuntimeError(
                            f"Godot progression segment failed; report: {segment_report}"
                        )
            print(
                f"Verified {len(report['checks'])} account/multiplayer checks; report: {report_path}"
            )
    finally:
        if not auth.logout():
            print(
                "Fixture-session logout could not complete; accounts were retained for inspection."
            )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
