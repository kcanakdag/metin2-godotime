#!/usr/bin/env python3
"""Exercise the three-step Sword+0 combo and authoritative roots with two clients."""

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


def schema_text(game_server: str, database: str) -> str:
    url = f"{game_server}/v1/database/{urllib.parse.quote(database, safe='')}/schema?version=10"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            schema = json.load(response)
    except (OSError, ValueError, urllib.error.HTTPError) as error:
        raise RuntimeError(
            "The selected game route does not expose the combo database schema "
            f"({type(error).__name__})."
        ) from None
    if not isinstance(schema, dict):
        raise RuntimeError("The selected game route returned an invalid database schema.")
    return json.dumps(schema, separators=(",", ":"))


def trusted_definition_hash() -> str:
    definitions = json.loads((ROOT / "server/content/p0-warrior-dog/actions.v1.json").read_text())
    value = definitions.get("gameplay_definition_hash")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RuntimeError("Trusted server definitions have no valid gameplay hash.")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:3210")
    parser.add_argument("--game-server")
    parser.add_argument("--database", required=True)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument(
        "--report", type=Path, default=ROOT / ".local/p2-rootmotion/combo-report.json"
    )
    options = parser.parse_args()
    if not options.database.startswith("mt2-p2-"):
        raise RuntimeError("Combo smoke requires a disposable mt2-p2- database.")
    report_path = options.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"passed": False, "database": options.database, "checks": []}, indent=2) + "\n"
    )
    auth = AuthClient(options.server)
    try:
        health, _ = auth.request("/auth/health")
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise RuntimeError("The selected origin does not expose a healthy /auth service.")
        game_server = (options.game_server or auth.server).rstrip("/")
        schema = schema_text(game_server, options.database)
        required_schema = (
            "combo_step",
            "combo_chain_revision",
            "pending_attack_action_revision",
            "root_motion_started_at_us",
            "perform_attack",
            "combat_target_view",
        )
        if any(name not in schema for name in required_schema):
            raise RuntimeError("The selected database does not expose the protocol 8 combo schema.")
        definition_hash = trusted_definition_hash()
        with tempfile.TemporaryDirectory(prefix="root-motion-", dir=ROOT / ".local") as scratch:
            stage = Path(scratch)
            stage_project(stage)
            combo_script = Path("tests/combo_smoke.gd")
            root_script = Path("tests/root_motion_smoke.gd")
            for script in (combo_script, root_script):
                (stage / script).write_bytes((ROOT / "client" / script).read_bytes())
            run_godot(
                options.godot,
                stage,
                auth,
                report_path.with_suffix(".import.log"),
                "--editor",
                "--import",
                "--quit",
                "--lsp-port",
                "6365",
                "--dap-port",
                "6366",
            )
            for script, label in (
                ("spacetime_bindings/schema/module_game_client.gd", "bindings"),
                ("tests/combo_smoke.gd", "smoke"),
                ("tests/root_motion_smoke.gd", "root-motion-smoke"),
            ):
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
            tokens = [auth.create_account(f"combo_{suffix}_{index}") for index in range(2)]
            fixture = stage / "combo-config.json"
            private_report = stage / "combo-report.json"
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
                    "res://tests/root_motion_smoke.gd",
                    "--",
                    "--account-config",
                    str(fixture),
                    timeout=240,
                )
            finally:
                if private_report.is_file():
                    report_path.write_text(auth.redact(private_report.read_text()))
            if not private_report.is_file():
                raise RuntimeError("Godot did not produce its combo report.")
            report = json.loads(report_path.read_text())
            if not report.get("passed") or "MT2_MULTIPLAYER_SMOKE PASS" not in output:
                raise RuntimeError(f"Godot combo checks failed; report: {report_path}")
            print(f"Verified {len(report['checks'])} combo checks; report: {report_path}")
    finally:
        if not auth.logout():
            print("Fixture-session logout could not complete; accounts remain for inspection.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
