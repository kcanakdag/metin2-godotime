#!/usr/bin/env python3
"""Exercise physical damage and private combat-stat projections with two clients."""

from __future__ import annotations

import argparse
import hashlib
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


def run_segment(
    options,
    stage,
    auth,
    game_server,
    definition_hash,
    selected_script,
    tokens,
    target_kills,
    report_path,
    tested_sources,
):
    fixture = stage / f"physical-config-{target_kills}.json"
    private_report = stage / f"physical-report-{target_kills}.json"
    descriptor = os.open(fixture, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(
            {
                "server": game_server,
                "database": options.database,
                "tokens": tokens,
                "definition_hash": definition_hash,
                "report": str(private_report),
                "target_kills": target_kills,
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
            "res://" + str(selected_script),
            "--",
            "--account-config",
            str(fixture),
            *(["--class-id", str(options.class_id)] if options.class_id is not None else []),
            timeout=360 if options.scenario == "classes" else 240,
        )
    finally:
        if private_report.is_file():
            result = json.loads(private_report.read_text())
            result["scenario"] = options.scenario
            result["class_id"] = options.class_id
            result["tested_sources"] = tested_sources
            result["staged_sources_unchanged"] = all(
                hashlib.sha256((stage / relative).read_bytes()).hexdigest() == digest
                for relative, digest in tested_sources.items()
            )
            result["passed"] = bool(result.get("passed")) and result["staged_sources_unchanged"]
            report_path.write_text(auth.redact(json.dumps(result, indent=2) + "\n"))
    if not private_report.is_file():
        raise RuntimeError("Godot did not produce its physical report.")
    report = json.loads(report_path.read_text())
    if not report.get("passed") or "MT2_MULTIPLAYER_SMOKE PASS" not in output:
        raise RuntimeError(f"Godot physical checks failed; report: {report_path}")
    print(f"Verified {len(report['checks'])} physical checks; report: {report_path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:3210")
    parser.add_argument("--game-server")
    parser.add_argument("--database", required=True)
    parser.add_argument(
        "--scenario",
        choices=[
            "melee",
            "finisher",
            "growth",
            "lifecycle",
            "recovery",
            "security",
            "population",
            "npcs",
            "classes",
        ],
        default="melee",
    )
    parser.add_argument(
        "--class-id",
        type=int,
        choices=range(4),
        help="Focus the classes scenario on one class while validating the full private rosters",
    )
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument(
        "--population-profile", type=Path, default=ROOT / "content/worlds/yongan.population.json"
    )
    parser.add_argument(
        "--report", type=Path, default=ROOT / ".local/p2-physical/combat-report.json"
    )
    options = parser.parse_args()
    if options.class_id is not None and options.scenario != "classes":
        parser.error("--class-id requires --scenario classes")
    if not options.database.startswith("mt2-p2-"):
        raise RuntimeError("Physical smoke requires a disposable mt2-p2- database.")
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
            "special_area",
            "monster_force",
            "perform_attack",
            "combat_target_view",
            "display_attack_min",
            "display_attack_max",
            "display_defense",
            "display_attack_speed",
            "attack_speed_percent",
            "pending_attack_source_generation",
        )
        if any(name not in schema for name in required_schema):
            raise RuntimeError("The selected database does not expose the current physical schema.")
        definition_hash = trusted_definition_hash()
        with tempfile.TemporaryDirectory(prefix="physical-", dir=ROOT / ".local") as scratch:
            stage = Path(scratch)
            stage_project(stage)
            if options.scenario == "classes":
                (stage / "scripts/actors").mkdir(parents=True, exist_ok=True)
                (stage / "scripts/actors/attack_timing.gd").write_bytes(
                    (ROOT / "client/scripts/actors/attack_timing.gd").read_bytes()
                )
                (stage / "tests/character-catalog.json").write_bytes(
                    (ROOT / "client/assets/imported/characters/catalog.v1.json").read_bytes()
                )
                (stage / "tests/base-catalog.json").write_bytes(
                    (
                        ROOT / "client/assets/imported/content/p0-warrior-dog/manifest.v1.json"
                    ).read_bytes()
                )
            if options.scenario in ("population", "npcs"):
                from world_content import inspector, validate

                profile = json.loads(options.population_profile.read_text())
                expected = validate(profile, inspector(profile["map_id"]))
                (stage / "tests/population.json").write_text(json.dumps(expected, indent=2) + "\n")
            selected_script = Path(
                "tests/physical_"
                + ("combat" if options.scenario == "melee" else options.scenario)
                + "_smoke.gd"
            )
            scripts = [Path("tests/combo_smoke.gd"), selected_script]
            if options.scenario == "npcs":
                scripts.append(Path("tests/physical_population_smoke.gd"))
                (stage / "tests/npc-route.json").write_bytes(
                    (ROOT / "tests/fixtures/yongan-city-guard-route.json").read_bytes()
                )
            if options.scenario in ("finisher", "lifecycle"):
                scripts.extend(
                    [Path("tests/root_motion_smoke.gd"), Path("tests/finisher_smoke.gd")]
                )
            if options.scenario == "lifecycle":
                scripts.append(Path("tests/physical_finisher_smoke.gd"))
            if options.scenario in ("recovery", "security"):
                scripts.append(Path("tests/physical_combat_smoke.gd"))
            if options.scenario == "security":
                scripts.append(Path("tests/physical_recovery_smoke.gd"))
            if options.scenario == "growth":
                scripts.append(Path("tests/physical_combat_smoke.gd"))
                (stage / "tests/physical-stat-cases.json").write_bytes(
                    (ROOT / "tests/fixtures/physical-stat-cases.json").read_bytes()
                )
            for script in scripts:
                (stage / script).write_bytes((ROOT / "client" / script).read_bytes())
            tested_sources = {
                str(path.relative_to(stage)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(stage.rglob("*"))
                if path.is_file()
            }
            report_path.with_suffix(".inputs.json").write_text(
                json.dumps(
                    {
                        "scenario": options.scenario,
                        "class_id": options.class_id,
                        "definition_hash": definition_hash,
                        "tested_sources": tested_sources,
                    },
                    indent=2,
                )
                + "\n"
            )
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
            for script in [Path("spacetime_bindings/schema/module_game_client.gd"), *scripts]:
                run_godot(
                    options.godot,
                    stage,
                    auth,
                    report_path.with_suffix(f".{script.stem}-parse.log"),
                    "--check-only",
                    "--script",
                    "res://" + str(script),
                )

            suffix = uuid.uuid4().hex[:12]
            tokens = [auth.create_account(f"phys_{suffix}_{index}") for index in range(2)]
            targets = [5, 10, 15, 20] if options.scenario == "growth" else [0]
            combined = {
                "passed": False,
                "database": options.database,
                "scenario": options.scenario,
                "class_id": options.class_id,
                "checks": [],
                "segments": [],
            }
            for index, target in enumerate(targets):
                if index:
                    tokens = [auth.game_token(account) for account in range(2)]
                segment_report = (
                    report_path.with_suffix(f".growth-{target}.json") if target else report_path
                )
                try:
                    run_segment(
                        options,
                        stage,
                        auth,
                        game_server,
                        definition_hash,
                        selected_script,
                        tokens,
                        target,
                        segment_report,
                        tested_sources,
                    )
                finally:
                    if target and segment_report.is_file():
                        result = json.loads(segment_report.read_text())
                        combined["checks"].extend(
                            {**check, "name": f"kills_{target}_" + check["name"]}
                            for check in result.get("checks", [])
                        )
                        combined["segments"].append(
                            {
                                "target_kills": target,
                                "passed": result.get("passed", False),
                                "report": str(segment_report),
                            }
                        )
                        combined["passed"] = len(combined["segments"]) == 4 and all(
                            row["passed"] for row in combined["segments"]
                        )
                        report_path.write_text(json.dumps(combined, indent=2) + "\n")
            if options.scenario == "growth":
                print(
                    f"Verified {len(combined['checks'])} physical growth checks; report: {report_path}",
                    flush=True,
                )
    finally:
        if not auth.logout():
            print("Fixture-session logout could not complete; accounts remain for inspection.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
