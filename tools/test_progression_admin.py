#!/usr/bin/env python3
"""Run the two-phase authenticated progression-admin smoke on a disposable P2 database."""

from __future__ import annotations

import argparse
import json
import math
import operator
import os
import secrets
import shutil
import struct
import subprocess
import tempfile
import uuid
from pathlib import Path

from progression_operator import AuthSession, OperatorError, http_origin, private_json
from skill_formulas import VARIABLES

ROOT = Path(__file__).resolve().parents[1]
BUFF_PHASES = {"buff", "buff_hud", "buff_death", "buff_combat", "buff_movement"}
BUFF_SKILLS = (3, 4, 19)
BUFF_LEVEL = 5
BUFF_RANK = 1
BUFF_QUANT_LEVEL = 20
BUFF_QUANT_RANK = 20


def evaluate_skill_program(program: object, variables: list[float]) -> float:
    """Evaluate one bounded catalog formula with server-compatible truncation."""
    if not isinstance(program, list) or not program or len(program) > 128:
        raise OperatorError("Self-buff catalog formula is invalid.")
    stack: list[float] = []
    binary = {
        "add": operator.add,
        "sub": operator.sub,
        "mul": operator.mul,
        "div": operator.truediv,
    }
    for instruction in program:
        if not isinstance(instruction, dict):
            raise OperatorError("Self-buff catalog instruction is invalid.")
        op = str(instruction.get("op", ""))
        if op == "constant":
            value = float(instruction["value"])
        elif op == "variable":
            index = instruction.get("index")
            if not isinstance(index, int) or not 0 <= index < len(variables):
                raise OperatorError("Self-buff catalog variable is invalid.")
            value = variables[index]
        elif op in ("neg", "floor"):
            if not stack:
                raise OperatorError("Self-buff catalog formula stack underflow.")
            operand = stack.pop()
            value = -operand if op == "neg" else math.floor(operand)
        elif op in binary:
            if len(stack) < 2:
                raise OperatorError("Self-buff catalog formula stack underflow.")
            right = stack.pop()
            left = stack.pop()
            if op == "div" and right == 0:
                raise OperatorError("Self-buff catalog formula divides by zero.")
            value = binary[op](left, right)
        else:
            raise OperatorError(f"Unsupported self-buff catalog operation: {op}")
        if not math.isfinite(value) or abs(value) > 1_000_000_000_000:
            raise OperatorError("Self-buff catalog arithmetic exceeds bounds.")
        stack.append(value)
    if len(stack) != 1:
        raise OperatorError("Self-buff catalog formula result is ambiguous.")
    return stack[0]


def buff_expectation(
    catalog_path: Path,
    vnum: int,
    level: int,
    rank: int,
    character_catalog_path: Path | None = None,
) -> dict[str, object]:
    """Derive the exact capture for a selected self-buff skill rank and level."""
    if not 1 <= level <= 99 or not 1 <= rank <= 20:
        raise OperatorError("Self-buff qualification level or rank is outside runtime bounds.")
    character_catalog_path = character_catalog_path or (
        ROOT / "client/assets/imported/characters/catalog.v1.json"
    )
    try:
        catalog = json.loads(catalog_path.read_text())
        characters = json.loads(character_catalog_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise OperatorError(f"Cannot read self-buff qualification catalogs: {error}") from error
    if (
        not isinstance(catalog, dict)
        or catalog.get("schema") != "mt2spacetime.skills"
        or not isinstance(catalog.get("skills"), list)
        or not isinstance(catalog.get("rank_power_percent"), list)
    ):
        raise OperatorError("Self-buff skill catalog has an unsupported schema.")
    skills = [
        row
        for row in catalog["skills"]
        if isinstance(row, dict) and int(row.get("vnum", 0)) == vnum
    ]
    if len(skills) != 1:
        raise OperatorError(f"Self-buff skill {vnum} is missing or ambiguous.")
    skill = skills[0]
    buff = skill.get("buff")
    if skill.get("handler") != "self_buff_v1" or not isinstance(buff, dict):
        raise OperatorError(f"Skill {vnum} is not a compiled self-buff.")
    try:
        power = int(catalog["rank_power_percent"][rank])
    except (IndexError, TypeError, ValueError) as error:
        raise OperatorError("Self-buff rank power table is invalid.") from error
    if not 1 <= power <= 100:
        raise OperatorError("Self-buff rank power is outside runtime bounds.")
    if not isinstance(characters, dict) or not isinstance(characters.get("classes"), list):
        raise OperatorError("Character catalog has an unsupported schema.")
    classes = [
        row
        for row in characters["classes"]
        if isinstance(row, dict) and int(row.get("class_id", -1)) == int(skill["class_id"])
    ]
    if len(classes) != 1 or not isinstance(classes[0].get("initial_points"), dict):
        raise OperatorError("Self-buff class initial stats are missing or ambiguous.")
    initial = classes[0]["initial_points"]
    variables = [0.0] * len(VARIABLES)
    for name in ("str", "dex", "con", "iq"):
        source = {
            "str": "strength",
            "dex": "dexterity",
            "con": "vitality",
            "iq": "intelligence",
        }[name]
        variables[VARIABLES.index(name)] = float(initial[source])
    variables[VARIABLES.index("lv")] = float(level)
    # Server capture converts integer rank power to f32 before widening to f64.
    variables[VARIABLES.index("k")] = struct.unpack("f", struct.pack("f", power / 100.0))[0]
    cost = int(evaluate_skill_program(buff.get("sp_cost"), variables))
    cooldown_seconds = int(evaluate_skill_program(buff.get("cooldown"), variables))
    modifiers = buff.get("modifiers")
    if not isinstance(modifiers, list) or not 1 <= len(modifiers) <= 4:
        raise OperatorError("Self-buff modifier list is invalid.")
    effects: dict[str, int] = {}
    durations: list[int] = []
    for modifier in modifiers:
        if not isinstance(modifier, dict) or not isinstance(modifier.get("point"), str):
            raise OperatorError("Self-buff modifier is invalid.")
        point = modifier["point"]
        if point in effects:
            raise OperatorError("Self-buff modifier point is duplicated.")
        factor = modifier.get("power_percent_factor")
        if factor is not None:
            if not isinstance(factor, int) or not 0 <= factor <= 100_000:
                raise OperatorError("Self-buff power-percent factor is invalid.")
            value = math.trunc(power * factor / 100)
        else:
            value = int(evaluate_skill_program(modifier.get("value"), variables))
        duration = int(evaluate_skill_program(modifier.get("duration"), variables))
        if not 1 <= duration <= 86_400:
            raise OperatorError("Self-buff duration is outside runtime bounds.")
        effects[point] = value
        durations.append(duration)
    if len(set(durations)) != 1:
        raise OperatorError("Qualification requires one shared self-buff duration.")
    expected_cost = int(skill["rank_costs"][rank])
    expected_cooldown = int(skill["rank_cooldowns_us"][rank])
    if cost != expected_cost or cooldown_seconds * 1_000_000 != expected_cooldown:
        raise OperatorError("Self-buff capture disagrees with compiled rank tables.")
    return {
        "vnum": vnum,
        "level": level,
        "rank": rank,
        "name": str(skill["name"]),
        "cost": cost,
        "cooldown_us": cooldown_seconds * 1_000_000,
        "duration_ticks": durations[0],
        "action_suffix": "." + str(skill["motion"]),
        "effects": effects,
    }


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


def stage_project(stage: Path, *, client_input: bool = False) -> None:
    if client_input:
        shutil.copytree(ROOT / "client/scripts", stage / "scripts")
        shutil.copytree(ROOT / "client/assets/imported/skills", stage / "assets/imported/skills")
    for directory in ("addons/SpacetimeDB", "spacetime_bindings"):
        shutil.copytree(ROOT / "client" / directory, stage / directory)
    for source, destination in (
        (ROOT / "client/scripts/net/game_connection.gd", stage / "scripts/net/game_connection.gd"),
        (ROOT / "tools/progression_admin_smoke.gd", stage / "tests/progression_admin_smoke.gd"),
        (ROOT / "tools/skill_reaction_smoke.gd", stage / "tests/skill_reaction_smoke.gd"),
        (ROOT / "tools/skill_batch_smoke.gd", stage / "tests/skill_batch_smoke.gd"),
        (ROOT / "tools/charge_smoke.gd", stage / "tests/charge_smoke.gd"),
        (ROOT / "tools/buff_smoke.gd", stage / "tests/buff_smoke.gd"),
        (ROOT / "tools/buff_hud_smoke.gd", stage / "tests/buff_hud_smoke.gd"),
        (ROOT / "tools/buff_death_smoke.gd", stage / "tests/buff_death_smoke.gd"),
        (ROOT / "tools/buff_combat_smoke.gd", stage / "tests/buff_combat_smoke.gd"),
        (ROOT / "tools/buff_movement_smoke.gd", stage / "tests/buff_movement_smoke.gd"),
        (ROOT / "tools/charge_strike_smoke.gd", stage / "tests/charge_strike_smoke.gd"),
        (ROOT / "tools/crush_smoke.gd", stage / "tests/crush_smoke.gd"),
        (ROOT / "tools/crush_death_smoke.gd", stage / "tests/crush_death_smoke.gd"),
        (ROOT / "tools/crush_overlap_smoke.gd", stage / "tests/crush_overlap_smoke.gd"),
        (ROOT / "tools/charge_input_smoke.gd", stage / "tests/charge_input_smoke.gd"),
        (ROOT / "tools/charge_moving_smoke.gd", stage / "tests/charge_moving_smoke.gd"),
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
        "buff": "buff_smoke.gd",
        "buff_hud": "buff_hud_smoke.gd",
        "buff_death": "buff_death_smoke.gd",
        "buff_combat": "buff_combat_smoke.gd",
        "buff_movement": "buff_movement_smoke.gd",
        "charge_strike": "charge_strike_smoke.gd",
        "crush": "crush_smoke.gd",
        "crush_death": "crush_death_smoke.gd",
        "crush_overlap": "crush_overlap_smoke.gd",
        "charge_input": "charge_input_smoke.gd",
        "charge_moving": "charge_moving_smoke.gd",
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
    timeout = 240 if str(config["mode"]) in {"buff_combat", "buff_movement"} else 120
    try:
        process = subprocess.run(
            command,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
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
            "buff",
            "buff_hud",
            "buff_death",
            "buff_combat",
            "buff_movement",
            "charge_strike",
            "crush",
            "crush_death",
            "crush_overlap",
            "charge_input",
            "charge_moving",
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
    parser.add_argument(
        "--buff-skill",
        type=int,
        choices=BUFF_SKILLS,
        default=3,
        help=(
            "Self-buff qualified by buff, buff_hud, buff_death, buff_combat or "
            "buff_movement (default: Berserk, 3)"
        ),
    )
    parser.add_argument("--skill-catalog", type=Path)
    parser.add_argument("--ui-package", type=Path)
    options = parser.parse_args()
    if options.phase in BUFF_PHASES and not options.skill_catalog:
        parser.error(f"{options.phase} requires --skill-catalog")
    if options.phase == "buff_hud" and not options.ui_package:
        parser.error("buff_hud requires --ui-package")
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
            stage_project(stage, client_input=mode in {"charge_input", "charge_moving", "buff_hud"})
            if mode == "buff_hud":
                shutil.copy2(
                    options.skill_catalog, stage / "assets/imported/skills/catalog.v1.json"
                )
                shutil.copytree(options.ui_package, stage / "assets/imported/ui")
                item = Path("assets/imported/content/p0-warrior-dog/manifest.v1.json")
                (stage / item).parent.mkdir(parents=True)
                shutil.copy2(ROOT / "client" / item, stage / item)
            if mode in {"buff_combat", "buff_movement"}:
                buff_level, buff_rank = BUFF_QUANT_LEVEL, BUFF_QUANT_RANK
            else:
                buff_level, buff_rank = BUFF_LEVEL, BUFF_RANK
            buff = (
                buff_expectation(
                    options.skill_catalog.resolve(),
                    options.buff_skill,
                    buff_level,
                    buff_rank,
                )
                if mode in BUFF_PHASES
                else {}
            )
            result = run_godot(
                options.godot,
                stage,
                {
                    "mode": mode,
                    "reaction_skill": options.reaction_skill or 1,
                    "buff": buff,
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
