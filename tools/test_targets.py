#!/usr/bin/env python3
"""Exercise private target locking against a disposable dual-Wild-Dog module."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from test_accounts import ROOT, AuthClient, run_godot, stage_project


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:3210")
    parser.add_argument("--game-server")
    parser.add_argument("--database", required=True)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--report", type=Path, default=ROOT / ".local/targets-report.json")
    options = parser.parse_args()
    report_path = options.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
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
            "The selected game route does not expose the target database schema "
            f"({type(error).__name__})."
        ) from None
    schema_text = json.dumps(schema, separators=(",", ":"))
    if "combat_target_view" not in schema_text or "select_combat_target" not in schema_text:
        raise RuntimeError("The selected database does not expose the target-locking schema.")
    try:
        with tempfile.TemporaryDirectory(prefix="targets-", dir=ROOT / ".local") as scratch:
            stage = Path(scratch)
            stage_project(stage)
            target_script = Path("tests/target_smoke.gd")
            (stage / target_script).write_bytes((ROOT / "client" / target_script).read_bytes())
            definitions = json.loads(
                (ROOT / "server/content/p0-warrior-dog/actions.v1.json").read_text()
            )
            definition_hash = definitions.get("gameplay_definition_hash")
            if not isinstance(definition_hash, str) or not re.fullmatch(
                r"[0-9a-f]{64}", definition_hash
            ):
                raise RuntimeError("Trusted server definitions have no valid gameplay hash.")
            run_godot(
                options.godot,
                stage,
                auth,
                report_path.with_suffix(".import.log"),
                "--editor",
                "--import",
                "--quit",
                "--lsp-port",
                "6265",
                "--dap-port",
                "6266",
            )
            run_godot(
                options.godot,
                stage,
                auth,
                report_path.with_suffix(".parse.log"),
                "--check-only",
                "--script",
                "res://tests/target_smoke.gd",
            )
            suffix = uuid.uuid4().hex[:12]
            tokens = [auth.create_account(f"target_{suffix}_{index}") for index in range(2)]
            fixture = stage / "target-config.json"
            private_report = stage / "target-report.json"
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
                    "res://tests/target_smoke.gd",
                    "--",
                    "--account-config",
                    str(fixture),
                    timeout=180,
                )
            finally:
                if private_report.is_file():
                    report_path.write_text(auth.redact(private_report.read_text()))
            if not private_report.is_file():
                raise RuntimeError("Godot did not produce its target report.")
            report = json.loads(report_path.read_text())
            if not report.get("passed") or "MT2_MULTIPLAYER_SMOKE PASS" not in output:
                raise RuntimeError(f"Godot target checks failed; report: {report_path}")
            print(f"Verified {len(report['checks'])} target checks; report: {report_path}")
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
