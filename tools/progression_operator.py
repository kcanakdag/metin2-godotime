#!/usr/bin/env python3
"""Grant or revoke the fixed progression-operator capability through normal auth."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_PATTERN = re.compile(r"[0-9a-f]{64}")
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


class OperatorError(RuntimeError):
    """A bounded operator-facing failure without credential content."""


def http_origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise OperatorError("--server must be an HTTP(S) origin exposing /auth and the game API.")
    return value.rstrip("/")


def private_json(path: Path, description: str) -> dict[str, object]:
    try:
        metadata = path.stat()
    except OSError as error:
        raise OperatorError(f"Cannot read {description} file ({type(error).__name__}).") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or path.is_symlink()
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or metadata.st_size > 16_384
    ):
        raise OperatorError(f"{description} file must be regular and readable only by its owner.")
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise OperatorError(f"Cannot parse {description} file ({type(error).__name__}).") from None
    if not isinstance(value, dict):
        raise OperatorError(f"{description} file must contain a JSON object.")
    return value


def credentials(path: Path | None) -> tuple[str, str]:
    if path is None:
        username = input("Bootstrap operator username: ").strip()
        password = getpass.getpass("Bootstrap operator password: ")
    else:
        value = private_json(path, "credential")
        username = value.get("username")
        password = value.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            raise OperatorError("Credential file requires string username and password fields.")
        username = username.strip()
    if not username or not password:
        raise OperatorError("Operator username and password must be nonempty.")
    return username, password


def reason_text(path: Path | None) -> str:
    if path is None:
        value = input("Audit reason (3-160 printable characters): ").strip()
    else:
        try:
            metadata = path.stat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or path.is_symlink()
                or stat.S_IMODE(metadata.st_mode) & 0o077
                or metadata.st_size > 1024
            ):
                raise OperatorError("Reason file must be regular and readable only by its owner.")
            value = path.read_text().strip()
        except OSError as error:
            raise OperatorError(f"Cannot read reason file ({type(error).__name__}).") from None
    if not 3 <= len(value) <= 160 or not value.isprintable():
        raise OperatorError("Audit reason must be 3-160 printable characters.")
    return value


class AuthSession:
    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.session = ""
        self.secrets: list[str] = []

    def redact(self, value: str | bytes | None) -> str:
        text = value.decode(errors="replace") if isinstance(value, bytes) else value or ""
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, "[credential redacted]")
        return JWT_PATTERN.sub("[JWT redacted]", text)

    def request(
        self, path: str, body: dict[str, object] | None = None, bearer: str = ""
    ) -> tuple[object, str]:
        headers = {"Accept": "application/json", "Origin": self.origin}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if bearer:
            headers["Authorization"] = "Bearer " + bearer
        request = urllib.request.Request(self.origin + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                value = json.load(response)
                replacement = response.headers.get("set-auth-token", "")
        except urllib.error.HTTPError as error:
            retry = error.headers.get("X-Retry-After", "")
            suffix = f" Retry after {retry} seconds." if retry.isdigit() else ""
            raise OperatorError(
                f"Authentication request returned HTTP {error.code}.{suffix}"
            ) from None
        except (OSError, ValueError) as error:
            raise OperatorError(
                f"Authentication request failed ({type(error).__name__})."
            ) from None
        if replacement:
            self.secrets.append(replacement)
        return value, replacement

    def sign_in(self, username: str, password: str) -> str:
        self.secrets.extend((username, password))
        _, self.session = self.request(
            "/auth/sign-in/username",
            {"username": username, "password": password, "rememberMe": False},
        )
        if not self.session:
            raise OperatorError("Sign-in did not return an account session.")
        value, replacement = self.request("/auth/token", bearer=self.session)
        if replacement:
            self.session = replacement
        if not isinstance(value, dict) or not isinstance(value.get("token"), str):
            raise OperatorError("Authentication did not return a game credential.")
        token = value["token"]
        if not JWT_PATTERN.fullmatch(token):
            raise OperatorError("Authentication returned an invalid game credential.")
        self.secrets.append(token)
        return token

    def close(self) -> None:
        if not self.session:
            return
        try:
            self.request("/auth/sign-out", {}, self.session)
        except OperatorError:
            pass
        self.session = ""


def stage_driver(stage: Path) -> None:
    for directory in ("addons/SpacetimeDB", "spacetime_bindings"):
        source = ROOT / "client" / directory
        if not source.is_dir():
            raise OperatorError(
                "Generated client bindings are missing; publish P2 and regenerate them."
            )
        shutil.copytree(source, stage / directory)
    destination = stage / "tests/progression_operator_driver.gd"
    destination.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "tools/progression_operator_driver.gd", destination)
    (stage / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="MT2 Progression Operator"\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
    )


def atomic_report(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run_driver(
    godot: str,
    stage: Path,
    config_path: Path,
    auth: AuthSession,
    log_path: Path,
) -> dict[str, object]:
    environment = os.environ.copy()
    environment["XDG_DATA_HOME"] = str(stage / ".data")
    environment["XDG_CONFIG_HOME"] = str(stage / ".config")
    try:
        import_process = subprocess.run(
            [godot, "--headless", "--path", str(stage), "--editor", "--import", "--quit"],
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        log_path.write_text(auth.redact(error.stdout))
        raise OperatorError(
            f"Operator driver project import timed out; sanitized log: {log_path}"
        ) from None
    if import_process.returncode:
        log_path.write_text(auth.redact(import_process.stdout))
        raise OperatorError(f"Operator driver project import failed; sanitized log: {log_path}")
    command = [
        godot,
        "--headless",
        "--path",
        str(stage),
        "--script",
        "res://tests/progression_operator_driver.gd",
        "--",
        "--operator-config",
        str(config_path),
    ]
    try:
        result = subprocess.run(
            command,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=45,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        log_path.write_text(auth.redact(error.stdout))
        raise OperatorError(f"Operator driver timed out; sanitized log: {log_path}") from None
    output = auth.redact(result.stdout)
    log_path.write_text(output)
    report_path = stage / "operator-result.json"
    if result.returncode or not report_path.is_file():
        raise OperatorError(f"Operator driver failed; sanitized log: {log_path}")
    try:
        report = json.loads(report_path.read_text())
    except (OSError, ValueError) as error:
        raise OperatorError(
            f"Operator driver returned an invalid result ({type(error).__name__})."
        ) from None
    if not isinstance(report, dict):
        raise OperatorError("Operator driver returned an invalid result object.")
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("action", choices=("grant", "revoke"))
    result.add_argument("target_account", help="Exact existing lowercase 64-hex account identity")
    result.add_argument("--server", default="http://127.0.0.1:8186")
    result.add_argument(
        "--game-server",
        help="Direct game origin when it differs from the origin exposing /auth.",
    )
    result.add_argument("--database", required=True)
    result.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    result.add_argument("--credential-file", type=Path)
    result.add_argument("--reason-file", type=Path)
    result.add_argument(
        "--report", type=Path, default=ROOT / ".local/progression-operator-report.json"
    )
    return result


def main() -> None:
    options = parser().parse_args()
    origin = http_origin(options.server)
    game_origin = http_origin(options.game_server or options.server)
    if not IDENTITY_PATTERN.fullmatch(options.target_account):
        raise OperatorError("target_account must be exact lowercase 64-hex.")
    if (
        not options.database
        or options.database != options.database.lower()
        or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
            for character in options.database
        )
    ):
        raise OperatorError("--database must be a lowercase database name.")
    enabled = options.action == "grant"
    report_path = options.report.resolve()
    run_id = uuid.uuid4().hex
    request_id = secrets.token_hex(16)
    report_base: dict[str, object] = {
        "run_id": run_id,
        "request_id": request_id,
        "applied": False,
        "status": "pending",
        "actor_account": "",
        "target_account": options.target_account,
        "enabled": enabled,
        "severity": "info",
        "message": "Operator request is pending.",
    }
    atomic_report(report_path, report_base)
    auth = AuthSession(origin)
    username = ""
    password = ""
    terminal_written = False
    try:
        username, password = credentials(options.credential_file)
        reason = reason_text(options.reason_file)
        game_token = auth.sign_in(username, password)
        username = ""
        password = ""
        (ROOT / ".local").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="progression-operator-", dir=ROOT / ".local"
        ) as raw:
            stage = Path(raw)
            stage_driver(stage)
            private_config = stage / "operator-config.json"
            descriptor = os.open(private_config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as handle:
                json.dump(
                    {
                        "server": game_origin,
                        "database": options.database,
                        "token": game_token,
                        "request_id": request_id,
                        "target_account": options.target_account,
                        "enabled": enabled,
                        "reason": reason,
                        "report": str(stage / "operator-result.json"),
                    },
                    handle,
                )
            game_token = ""
            result = run_driver(
                options.godot,
                stage,
                private_config,
                auth,
                report_path.with_suffix(".log"),
            )
        public_result = {
            "run_id": run_id,
            "request_id": request_id,
            "applied": result.get("applied") is True,
            "status": "applied" if result.get("applied") is True else "denied",
            "actor_account": result.get("actor_account", ""),
            "target_account": options.target_account,
            "enabled": enabled,
            "severity": result.get("severity", "error"),
            "message": result.get("message", "Operator request returned no feedback."),
        }
        atomic_report(report_path, public_result)
        terminal_written = True
        print(
            f"Progression operator request: {public_result['severity']}: "
            f"{public_result['message']} Report: {report_path}"
        )
        if not public_result["applied"]:
            raise OperatorError("The server denied the progression operator request.")
    except (OperatorError, EOFError, KeyboardInterrupt, OSError) as error:
        if not terminal_written:
            failed = report_base | {
                "status": "error",
                "severity": "error",
                "message": str(error)[:240] or "Operator request cancelled.",
            }
            atomic_report(report_path, failed)
        raise
    finally:
        username = ""
        password = ""
        auth.close()


if __name__ == "__main__":
    try:
        main()
    except (OperatorError, EOFError, KeyboardInterrupt, OSError) as error:
        raise SystemExit(str(error) or "Operator request cancelled.") from None
