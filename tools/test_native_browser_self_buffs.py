#!/usr/bin/env python3
"""Qualify protocol-31 self-buffs across the exported Web and Linux clients.

The two clients use independent existing QA accounts on one actual server.  The
owner alternates by skill so both ordinary client input paths, skill panels,
HUDs and presentation layers participate.  No database query or token grants
gameplay state; setup uses the ordinary authorized developer commands.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

from browser_snapshot import SnapshotUnavailableError, read_fresh_json_snapshot
from playwright.sync_api import sync_playwright
from progression_operator import private_json
from test_progression_admin import buff_expectation

ROOT = Path(__file__).resolve().parents[1]
OWNER_BY_SKILL = {3: "web", 4: "native", 19: "web"}


def database_scope_error(database: str, *, allowed_public_qa: str | None = None) -> str | None:
    """Reject broad databases; one explicitly named public QA database is allowed."""
    if database.startswith("mt2-p2-") or database == (allowed_public_qa or ""):
        return None
    return "Use a disposable mt2-p2- database; this replay spends skill points"


DESIRED_LEVEL = 12


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def private_write(path: Path, text: str) -> None:
    """Create command/log/report files with owner-only access from their first byte."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as destination:
        os.chmod(path, 0o600)
        destination.write(text)


def player_row(snapshot: dict, identity: str) -> dict:
    return next(
        (row for row in snapshot.get("player_rows", []) if row.get("identity") == identity),
        {},
    )


def rendered_position(snapshot: dict, identity: str) -> list[float] | None:
    row = next(
        (
            candidate
            for candidate in snapshot.get("rendered_actors", [])
            if candidate.get("identity") == identity
        ),
        {},
    )
    position = row.get("position")
    if (
        not isinstance(position, list)
        or len(position) != 3
        or not all(isinstance(value, (int, float)) for value in position)
    ):
        return None
    return [float(value) for value in position]


def own_buffs(snapshot: dict, identity: str) -> list[dict]:
    return [
        row
        for row in snapshot.get("buffs", [])
        if isinstance(row, dict)
        and row.get("character_id") == identity
        and not bool(row.get("paused", True))
    ]


def skill_row(snapshot: dict, vnum: int) -> dict:
    return next(
        (
            row
            for row in snapshot.get("ui", {}).get("skills", {}).get("rows", [])
            if int(row.get("skill_vnum", 0)) == vnum
        ),
        {},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--motion-catalog", type=Path, required=True)
    parser.add_argument(
        "--native",
        type=Path,
        default=ROOT / ".local/p6-self-buffs-export-r7/linux/MT2Spacetime.x86_64",
    )
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument(
        "--skill-vnums",
        default="3,4,19",
        help="Comma-separated self-buff vnums to exercise",
    )
    parser.add_argument("--skill-vnum", type=int, help="Run one self-buff instead")
    parser.add_argument("--expiry-timeout", type=float, default=180.0)
    parser.add_argument(
        "--allow-public-qa-database",
        metavar="NAME",
        help="Also accept this exact public QA database; the replay spends skill points",
    )
    args = parser.parse_args()

    if error := database_scope_error(
        args.database, allowed_public_qa=args.allow_public_qa_database
    ):
        parser.error(error)
    if not args.native.is_file():
        parser.error(f"Missing exported Linux test client: {args.native}")
    if not shutil.which("xvfb-run"):
        parser.error("The native client requires xvfb-run.")
    requested = (
        [args.skill_vnum]
        if args.skill_vnum is not None
        else [int(value) for value in args.skill_vnums.split(",") if value.strip()]
    )
    if not requested or len(set(requested)) != len(requested):
        parser.error("--skill-vnums must contain unique vnums")

    catalog = json.loads(args.catalog.read_text())
    motion_catalog = json.loads(args.motion_catalog.read_text())
    skills = {}
    for vnum in requested:
        definition = next(
            (row for row in catalog.get("skills", []) if int(row.get("vnum", -1)) == vnum),
            None,
        )
        if definition is None or definition.get("handler") != "self_buff_v1":
            parser.error(f"Skill {vnum} is not a catalogued self-buff")
        if vnum not in OWNER_BY_SKILL:
            parser.error(f"Skill {vnum} has no mixed-client owner assignment")
        expected = buff_expectation(args.catalog, vnum, DESIRED_LEVEL, 1)
        skills[vnum] = {
            "definition": definition,
            "expected": expected,
            "owner": OWNER_BY_SKILL[vnum],
        }

    fixture = private_json(args.fixture, "account fixture")
    accounts = fixture.get("accounts")
    if not isinstance(accounts, list) or len(accounts) != 2:
        parser.error("The fixture must contain two existing accounts")

    output = args.output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(output, 0o700)
    report_path = output / "desktop.json"
    command_path = output / "commands.json"
    checks: list[str] = []
    samples: dict[str, object] = {}
    browser_errors: list[str] = []
    network_errors: list[str] = []
    native_errors: list[str] = []
    retry_after: list[float] = []
    page = None
    process = None
    context = None
    browser = None
    log = None
    passed = False
    failure = ""
    sequence = 0
    native_snapshot_ready = False
    last_web_snapshot: dict = {}

    def redact(value: object) -> str:
        text = str(value)
        for account in accounts:
            for secret in account.values():
                if isinstance(secret, str) and secret:
                    text = text.replace(secret, "[redacted]")
        return re.sub(r"([?&]token=)[^ &]+", r"\1[redacted]", text)

    def web() -> dict:
        nonlocal last_web_snapshot
        assert page is not None
        snapshot = page.evaluate("() => JSON.parse(window.mt2Snapshot || '{}')")
        if isinstance(snapshot, dict):
            last_web_snapshot = snapshot
        return snapshot

    def desktop() -> dict:
        nonlocal native_snapshot_ready
        snapshot, _, _ = read_fresh_json_snapshot(report_path)
        native_snapshot_ready = True
        return snapshot

    def safe_desktop() -> dict:
        try:
            return desktop()
        except SnapshotUnavailableError:
            return {}

    def state(side: str) -> dict:
        return web() if side == "web" else safe_desktop()

    def command(side: str, action: str, **values: object) -> None:
        nonlocal sequence
        if side == "web":
            assert page is not None
            page.evaluate(
                "c => window.mt2Command(JSON.stringify(c))",
                {"action": action, **values},
            )
            return
        sequence += 1
        temporary = command_path.with_suffix(".tmp")
        private_write(
            temporary,
            json.dumps({"sequence": sequence, "action": action, **values}),
        )
        temporary.replace(command_path)

    def wait(name: str, predicate, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        last_notice = time.monotonic()
        while time.monotonic() < deadline:
            if predicate():
                checks.append(name)
                print("PASS " + name, flush=True)
                return
            if process is not None and process.poll() is not None:
                raise AssertionError(f"Exported native client exited during {name}")
            if timeout > 90 and time.monotonic() - last_notice >= 30:
                print("WAIT " + name, flush=True)
                last_notice = time.monotonic()
            time.sleep(0.05)
        raise AssertionError(name + " timed out")

    def wait_state(predicate, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return False

    def rate_limit_seconds(response) -> float:
        try:
            return float(response.headers.get("x-retry-after", "60"))
        except (TypeError, ValueError):
            return 60.0

    def login(side: str, account: dict) -> None:
        for attempt in range(5):
            retry_after.clear()
            command(
                side,
                "login",
                username=account["username"],
                password=account["password"],
            )
            if wait_state(
                lambda side=side: state(side).get("connection_state") == "lobby",
                60,
            ):
                checks.append(f"{side}_lobby")
                print(f"PASS {side}_lobby", flush=True)
                return
            if attempt == 4:
                raise AssertionError(f"{side}_lobby timed out")
            delay = min(max(retry_after) + 2.0, 75.0) if retry_after else 65.0
            print(f"RETRY {side}_lobby after {delay:.0f}s auth rate limit", flush=True)
            time.sleep(delay)

    def select_existing(side: str, slot: int) -> str:
        roster = state(side).get("account", {}).get("characters", [])
        row = next(
            (
                candidate
                for candidate in roster
                if int(candidate.get("slot", -1)) == slot
                and int(candidate.get("character_class", -1)) == 0
            ),
            None,
        )
        if row is None:
            raise AssertionError(f"{side} has no Warrior in existing slot {slot}")
        character_id = str(row["character_id"])
        command(side, "select", character_id=character_id)
        wait(
            f"{side}_existing_warrior_selected",
            lambda side=side, character_id=character_id: (
                state(side).get("account", {}).get("selected_id") == character_id
            ),
        )
        return character_id

    def enter_world(side: str) -> None:
        command(side, "enter")
        wait(
            f"{side}_enters_world",
            lambda side=side: state(side).get("connection_state") == "connected",
            120,
        )

    def owner_peer(skill_vnum: int) -> tuple[str, str]:
        owner = str(skills[skill_vnum]["owner"])
        return owner, "native" if owner == "web" else "web"

    def panel(side: str) -> dict:
        return state(side).get("ui", {}).get("skills", {})

    def control(side: str, vnum: int) -> dict:
        return next(
            row for row in panel(side).get("controls", []) if int(row.get("vnum", 0)) == vnum
        )

    def reveal(side: str, vnum: int) -> dict:
        if not panel(side).get("visible"):
            command(side, "key", name="k")
            wait(
                f"{side}_skill_panel_open",
                lambda side=side: panel(side).get("visible") is True,
            )
        for _ in range(30):
            entry = control(side, vnum)
            if entry.get("fully_visible"):
                return entry
            scroll_center = panel(side)["scroll_center"]
            delta = float(entry["slot_center"][1]) - float(scroll_center[1])
            delta = max(-1000.0, min(1000.0, delta))
            if side == "web":
                assert page is not None
                page.mouse.move(*scroll_center)
                page.mouse.wheel(0, delta)
            else:
                command(
                    "native",
                    "wheel",
                    x=float(scroll_center[0]),
                    y=float(scroll_center[1]),
                    delta=delta,
                )
            time.sleep(0.2)
        raise AssertionError(f"{side} skill control is not accessible: {vnum}")

    def bind_skill(side: str, vnum: int) -> None:
        entry = reveal(side, vnum)
        destination = state(side)["ui"]["quickslot_centers"][0]
        if side == "web":
            assert page is not None
            page.mouse.move(*entry["slot_center"])
            page.mouse.down()
            page.mouse.move(
                entry["slot_center"][0] + 20,
                entry["slot_center"][1],
                steps=4,
            )
            page.mouse.move(*destination, steps=12)
            page.mouse.up()
        else:
            command(
                "native",
                "drag",
                **{"from": entry["slot_center"], "to": destination},
            )
        wait(
            f"{side}_self_buff_quickslot_bound",
            lambda side=side, vnum=vnum: (
                int(state(side).get("ui", {}).get("quickslot_skill_bindings", [0])[0]) == vnum
            ),
        )
        command(side, "key", name="escape")
        wait(
            f"{side}_skill_panel_closed",
            lambda side=side: panel(side).get("visible") is False,
        )

    def set_owner_progression(side: str, vnum: int) -> None:
        current = next(
            (
                row
                for row in state(side).get("progression", [])
                if row.get("character_id") == state(side).get("identity")
            ),
            {},
        )
        if int(current.get("level", 0)) < DESIRED_LEVEL:
            command(
                side,
                "admin_command",
                command="level",
                argument=str(DESIRED_LEVEL),
            )
            wait(
                f"{side}_level_{DESIRED_LEVEL}_applied",
                lambda side=side: (
                    int(
                        next(
                            (
                                row
                                for row in state(side).get("progression", [])
                                if row.get("character_id") == state(side).get("identity")
                            ),
                            {},
                        ).get("level", 0)
                    )
                    >= DESIRED_LEVEL
                ),
                30,
            )
        if int(skill_row(state(side), vnum).get("rank", 0)) != 1:
            command(
                side,
                "admin_command",
                command="skill",
                argument=f"{vnum} 1",
            )
        wait(
            f"{side}_skill_{vnum}_rank_one",
            lambda side=side, vnum=vnum: int(skill_row(state(side), vnum).get("rank", 0)) == 1,
        )
        assert int(
            next(
                (
                    row
                    for row in state(side).get("progression", [])
                    if row.get("character_id") == state(side).get("identity")
                ),
                {},
            ).get("current_sp", 0)
        ) >= int(skills[vnum]["expected"]["cost"]), "Insufficient SP for the rank-one cast"

    def owner_buff(side: str) -> dict:
        identity = state(side)["identity"]
        rows = own_buffs(state(side), identity)
        return rows[0] if rows else {}

    def peer_owner_buff(peer_side: str, owner_id: str) -> dict:
        rows = own_buffs(state(peer_side), owner_id)
        return rows[0] if rows else {}

    def motion(side: str) -> dict:
        value = state(side).get("motion_effects", {})
        return value if isinstance(value, dict) else {}

    def wait_motion(
        side: str,
        baseline: int,
        expected: int,
        label: str,
        timeout: float = 12.0,
    ) -> dict:
        deadline = time.monotonic() + timeout
        observed: list[dict] = []
        while time.monotonic() < deadline:
            current = motion(side)
            observed.append(
                {
                    "spawned": int(current.get("spawned", -1)),
                    "active": int(current.get("active", -1)),
                    "error": str(current.get("error", "")),
                }
            )
            if (
                int(current.get("spawned", -1)) - baseline >= expected
                and int(current.get("active", 0)) > 0
                and not str(current.get("error", ""))
            ):
                checks.append(label)
                print("PASS " + label, flush=True)
                return {
                    "baseline": baseline,
                    "expected": expected,
                    "spawned": int(current.get("spawned", -1)),
                    "max_active": max(row["active"] for row in observed),
                    "samples": observed[-20:],
                }
            time.sleep(0.05)
        raise AssertionError(
            f"{label} timed out; spawned={motion(side).get('spawned')} "
            f"active={motion(side).get('active')} expected={expected}"
        )

    def capture(side: str, name: str) -> None:
        if side == "web":
            assert page is not None
            page.screenshot(path=str(output / name))
            return
        destination = output / name
        probe_capture = output / "desktop.png"
        probe_capture.unlink(missing_ok=True)
        command("native", "capture")
        wait(
            "native_capture_" + name,
            lambda probe_capture=probe_capture: probe_capture.is_file(),
        )
        probe_capture.replace(destination)

    def reconnect_owner(side: str, character_id: str) -> None:
        command(side, "disconnect")
        wait(
            f"{side}_owner_disconnected",
            lambda side=side: state(side).get("connection_state") == "disconnected",
        )
        command(side, "reconnect")
        wait(
            f"{side}_reconnect_returns",
            lambda side=side: state(side).get("connection_state") in {"lobby", "connected"},
            60,
        )
        if state(side).get("connection_state") == "lobby":
            command(side, "select", character_id=character_id)
            wait(
                f"{side}_reconnect_reselects_character",
                lambda side=side, character_id=character_id: (
                    state(side).get("account", {}).get("selected_id") == character_id
                ),
            )
            command(side, "enter")
        wait(
            f"{side}_reconnect_returns_to_world",
            lambda side=side: state(side).get("connection_state") == "connected",
            120,
        )

    def exercise(vnum: int, owner: str, peer: str, owner_id: str, peer_id: str) -> None:
        skill = skills[vnum]
        definition = skill["definition"]
        expected = skill["expected"]
        expected_cost = int(expected["cost"])
        expected_duration = int(expected["duration_ticks"])
        set_owner_progression(owner, vnum)
        wait(
            f"{owner}_skill_{vnum}_visible_in_panel",
            lambda owner=owner, vnum=vnum: bool(control(owner, vnum)),
        )
        bind_skill(owner, vnum)

        before_sp = int(
            next(
                (
                    row
                    for row in state(owner).get("progression", [])
                    if row.get("character_id") == owner_id
                ),
                {},
            ).get("current_sp", -1)
        )
        before_ready = int(skill_row(state(owner), vnum).get("ready_at_us", 0))
        before_sequences = {
            side: int(player_row(state(side), owner_id).get("attack_sequence", 0))
            for side in ("web", "native")
        }
        before_motion = {side: int(motion(side).get("spawned", -1)) for side in ("web", "native")}
        assert not owner_buff(owner), "Owner retained a stale self-buff before casting"
        assert not peer_owner_buff(peer, owner_id), "Peer received an owner buff before casting"

        capture(owner, f"self-buff-{vnum}-{owner}-before-cast.png")
        command(owner, "key", name="1")
        wait(
            f"skill_{vnum}_action_replicates",
            lambda owner_id=owner_id, before_sequences=before_sequences, vnum=vnum: all(
                int(player_row(state(side), owner_id).get("attack_sequence", 0))
                > before_sequences[side]
                and str(player_row(state(side), owner_id).get("attack_action_id", "")).endswith(
                    f".skill_{vnum}"
                )
                for side in ("web", "native")
            ),
        )
        action_id = str(player_row(state(owner), owner_id).get("attack_action_id", ""))
        links = motion_catalog.get("links", {}).get(action_id, [])
        expected_links = sum(
            1 for link in links if isinstance(link, dict) and bool(link.get("enabled", False))
        )
        assert expected_links > 0, f"No enabled motion-effect link for {action_id}"
        motion_samples = {
            side: wait_motion(
                side,
                before_motion[side],
                expected_links,
                f"skill_{vnum}_motion_{side}",
            )
            for side in ("web", "native")
        }
        wait(
            f"skill_{vnum}_status_owner_only",
            lambda owner=owner, peer=peer, owner_id=owner_id: (
                bool(owner_buff(owner)) and not peer_owner_buff(peer, owner_id)
            ),
        )
        wait(
            f"skill_{vnum}_sp_paid_once",
            lambda owner_id=owner_id, before_sp=before_sp, expected_cost=expected_cost: (
                int(
                    next(
                        (
                            row
                            for row in state(owner).get("progression", [])
                            if row.get("character_id") == owner_id
                        ),
                        {},
                    ).get("current_sp", -1)
                )
                == before_sp - expected_cost
            ),
        )
        wait(
            f"skill_{vnum}_hud_owner_only",
            lambda owner=owner, peer=peer, definition=definition: (
                int(state(owner).get("ui", {}).get("buffs", {}).get("count", -1)) == 1
                and state(owner).get("ui", {}).get("buffs", {}).get("rows", [{}])[0].get("name")
                == definition["name"]
                and int(state(peer).get("ui", {}).get("buffs", {}).get("count", -1)) == 0
            ),
        )
        wait(
            f"skill_{vnum}_cooldown_started",
            lambda owner=owner, vnum=vnum, before_ready=before_ready: (
                int(skill_row(state(owner), vnum).get("ready_at_us", 0)) > before_ready
            ),
        )
        first = owner_buff(owner)
        first_remaining = int(first["remaining_ticks"])
        first_id = str(first["id"])
        assert expected_duration - 1 <= first_remaining <= expected_duration, (
            f"Unexpected rank-one duration {first_remaining}; catalog expects {expected_duration}"
        )
        capture(owner, f"self-buff-{vnum}-{owner}-cast.png")
        capture(peer, f"self-buff-{vnum}-{peer}-peer-view.png")

        paid_sp = int(
            next(
                (
                    row
                    for row in state(owner).get("progression", [])
                    if row.get("character_id") == owner_id
                ),
                {},
            ).get("current_sp", -1)
        )
        paid_ready = int(skill_row(state(owner), vnum).get("ready_at_us", 0))
        paid_sequences = {
            side: int(player_row(state(side), owner_id).get("attack_sequence", 0))
            for side in ("web", "native")
        }
        command(owner, "key", name="1")
        time.sleep(1.0)
        assert (
            int(
                next(
                    (
                        row
                        for row in state(owner).get("progression", [])
                        if row.get("character_id") == owner_id
                    ),
                    {},
                ).get("current_sp", -1)
            )
            == paid_sp
        ), "Cooling cast paid SP twice"
        assert int(skill_row(state(owner), vnum).get("ready_at_us", 0)) == paid_ready, (
            "Cooling cast moved the cooldown"
        )
        assert {
            side: int(player_row(state(side), owner_id).get("attack_sequence", 0))
            for side in ("web", "native")
        } == paid_sequences, "Cooling cast replicated a second action"
        checks.append(f"skill_{vnum}_cooling_cast_rejected")
        print(f"PASS skill_{vnum}_cooling_cast_rejected", flush=True)

        wait(
            f"skill_{vnum}_duration_updates",
            lambda owner=owner, first_remaining=first_remaining: (
                bool(owner_buff(owner))
                and int(owner_buff(owner)["remaining_ticks"]) < first_remaining
            ),
            15,
        )
        before_reconnect = owner_buff(owner)
        capture(owner, f"self-buff-{vnum}-{owner}-before-reconnect.png")
        reconnect_owner(owner, owner_id)
        wait(
            f"skill_{vnum}_reconnect_restores_owner_status",
            lambda owner=owner, peer=peer, owner_id=owner_id, first_id=first_id: (
                bool(owner_buff(owner))
                and str(owner_buff(owner)["id"]) == first_id
                and int(state(owner).get("ui", {}).get("buffs", {}).get("count", -1)) == 1
                and not peer_owner_buff(peer, owner_id)
            ),
            30,
        )
        restored = owner_buff(owner)
        assert int(restored["remaining_ticks"]) <= int(before_reconnect["remaining_ticks"]), (
            "Reconnect replayed the full duration"
        )
        assert (
            int(
                next(
                    (
                        row
                        for row in state(owner).get("progression", [])
                        if row.get("character_id") == owner_id
                    ),
                    {},
                ).get("current_sp", -1)
            )
            == paid_sp
        ), "Reconnect replayed SP payment"
        assert {
            side: int(player_row(state(side), owner_id).get("attack_sequence", 0))
            for side in ("web", "native")
        } == paid_sequences, "Reconnect replayed the action"
        checks.append(f"skill_{vnum}_reconnect_does_not_replay")
        print(f"PASS skill_{vnum}_reconnect_does_not_replay", flush=True)
        capture(owner, f"self-buff-{vnum}-{owner}-after-reconnect.png")

        wait(
            f"skill_{vnum}_expires",
            lambda owner=owner, peer=peer, owner_id=owner_id: (
                not owner_buff(owner)
                and int(state(owner).get("ui", {}).get("buffs", {}).get("count", -1)) == 0
                and not peer_owner_buff(peer, owner_id)
            ),
            args.expiry_timeout,
        )
        assert (
            int(
                next(
                    (
                        row
                        for row in state(owner).get("progression", [])
                        if row.get("character_id") == owner_id
                    ),
                    {},
                ).get("current_sp", -1)
            )
            == paid_sp
        ), "Expiry replayed SP payment"
        assert {
            side: int(player_row(state(side), owner_id).get("attack_sequence", 0))
            for side in ("web", "native")
        } == paid_sequences, "Expiry replayed the action"
        checks.append(f"skill_{vnum}_expiry_does_not_replay")
        print(f"PASS skill_{vnum}_expiry_does_not_replay", flush=True)
        capture(owner, f"self-buff-{vnum}-{owner}-expired.png")

        samples[f"skill_{vnum}"] = {
            "skill_name": definition["name"],
            "owner": owner,
            "peer": peer,
            "expected_rank_one_cost": expected_cost,
            "expected_rank_one_duration": expected_duration,
            "sp_before": before_sp,
            "sp_after": paid_sp,
            "remaining_ticks_first": first_remaining,
            "buff_id": first_id,
            "action_id": action_id,
            "before_sequences": before_sequences,
            "paid_sequences": paid_sequences,
            "motion": motion_samples,
        }

    try:
        artifacts = {
            "native_binary_sha256": sha256(args.native),
            "native_pack_sha256": sha256(args.native.with_suffix(".pck")),
            "web_pack_sha256": sha256(args.native.parent.parent / "web/index.pck"),
            "web_wasm_sha256": sha256(args.native.parent.parent / "web/index.wasm"),
            "skill_catalog_sha256": sha256(args.catalog),
            "motion_catalog_file_sha256": sha256(args.motion_catalog),
            "motion_catalog_content_hash": str(motion_catalog.get("content_hash", "")),
        }
        samples["artifacts"] = artifacts
        private_write(output / "desktop.log", "")
        log = (output / "desktop.log").open("w")
        process = subprocess.Popen(
            [
                "xvfb-run",
                "-a",
                str(args.native.resolve()),
                "--",
                "--server",
                args.url,
                "--database",
                args.database,
                "--profile",
                "account-proof",
                "--probe-report",
                str(report_path),
                "--probe-commands",
                str(command_path),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={
                **os.environ,
                "XDG_DATA_HOME": str(output / "data"),
                "XDG_CONFIG_HOME": str(output / "config"),
            },
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=args.chrome,
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-crashpad",
                    "--enable-gpu",
                ],
            )
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            context.add_init_script("window.mt2ProbeEnabled = true;")
            page = context.new_page()
            page.on("pageerror", lambda error: browser_errors.append(redact(error)))
            page.on(
                "console",
                lambda message: (
                    browser_errors.append(redact(message.text))
                    if message.type == "error"
                    and message.text.lstrip().startswith(("ERROR:", "SCRIPT ERROR:", "Uncaught "))
                    else None
                ),
            )
            page.on(
                "requestfailed",
                lambda request: network_errors.append(
                    f"{request.method} {request.url}: {request.failure}"
                ),
            )
            page.on(
                "response",
                lambda response: (
                    network_errors.append(f"HTTP {response.status} {response.url}")
                    if response.status >= 400
                    else None
                ),
            )
            page.on(
                "response",
                lambda response: (
                    retry_after.append(rate_limit_seconds(response))
                    if response.status == 429
                    else None
                ),
            )
            page.goto(args.url, wait_until="domcontentloaded")
            wait(
                "both_exported_clients_boot",
                lambda: bool(state("web").get("account")) and bool(state("native").get("account")),
                90,
            )
            assert state("web").get("database") == state("native").get("database") == args.database
            checks.append("both_exports_target_requested_database")
            wait(
                "original_server_available_to_both_exports",
                lambda: (
                    state("web").get("account", {}).get("available")
                    and state("native").get("account", {}).get("available")
                ),
            )

            login("web", accounts[0])
            login("native", accounts[1])
            web_id = select_existing("web", 1)
            native_id = select_existing("native", 1)
            assert web_id != native_id
            assert state("web").get("account", {}).get("account_identity") != state("native").get(
                "account", {}
            ).get("account_identity")
            checks.append("independent_identities_and_rosters")
            enter_world("native")
            enter_world("web")
            assert str(state("web").get("motion_effects", {}).get("package_hash", "")) == str(
                motion_catalog.get("content_hash", "")
            )
            assert str(state("native").get("motion_effects", {}).get("package_hash", "")) == str(
                motion_catalog.get("content_hash", "")
            )
            checks.append("motion_package_identity_bound_on_both_clients")
            for side in ("web", "native"):
                assert not state(side).get("motion_effects", {}).get("error"), (
                    f"{side} motion effect error: {state(side)['motion_effects']['error']}"
                )
            checks.append("motion_package_loads_without_errors")
            wait(
                "mutual_rendered_peer_visibility",
                lambda: (
                    rendered_position(state("web"), native_id) is not None
                    and rendered_position(state("native"), web_id) is not None
                ),
                60,
            )
            for side, identity in (("web", web_id), ("native", native_id)):
                if own_buffs(state(side), identity):
                    print(
                        f"WAIT {side} selected character expiring a stale buff online",
                        flush=True,
                    )
                    wait(
                        f"{side}_stale_self_buff_expired_online",
                        lambda side=side, identity=identity: not own_buffs(state(side), identity),
                        args.expiry_timeout,
                    )
                assert not own_buffs(state(side), identity), (
                    f"{side} selected character retained a stale buff"
                )
            checks.append("selected_characters_start_without_stale_buffs")

            for vnum in requested:
                owner, peer = owner_peer(vnum)
                owner_id = web_id if owner == "web" else native_id
                peer_id = web_id if peer == "web" else native_id
                exercise(vnum, owner, peer, owner_id, peer_id)

            assert not browser_errors, "Browser engine errors: " + "; ".join(browser_errors[:3])
            checks.append("no_browser_engine_errors")
            native_state = desktop()
            assert not native_state.get("errors"), "Native probe errors: " + "; ".join(
                map(str, native_state["errors"][:3])
            )
            checks.append("no_native_probe_errors")
            passed = True
    except Exception as error:
        failure = redact(error) or type(error).__name__
        samples["failure_clients"] = []
        for side in ("web", "native"):
            try:
                current = state(side)
                samples["failure_clients"].append(
                    {
                        "side": side,
                        "connection_state": current.get("connection_state"),
                        "connection_message": current.get("connection_message"),
                        "account": current.get("account"),
                        "buffs": current.get("buffs"),
                        "errors": current.get("errors"),
                        "motion_effects": current.get("motion_effects"),
                        "progression": current.get("progression"),
                        "skill_effect_error": current.get("skill_effect_error"),
                        "world_entry_error": current.get("world_entry_error"),
                        "ui_notice": current.get("ui", {}).get("notice"),
                    }
                )
            except Exception as diagnostic_error:
                samples["failure_clients"].append({"side": side, "error": redact(diagnostic_error)})
        if page is not None and not page.is_closed():
            with contextlib.suppress(Exception):
                page.screenshot(path=str(output / "failure-web.png"))
        if process is not None and process.poll() is None:
            with contextlib.suppress(Exception):
                capture("native", "failure-native.png")
    finally:
        if process is not None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        if browser is not None:
            with contextlib.suppress(Exception):
                browser.close()
        if log is not None:
            log.close()
        if (output / "desktop.log").is_file():
            native_log = redact((output / "desktop.log").read_text())
            private_write(output / "desktop.log", native_log)
            if "SCRIPT ERROR:" in native_log or "\nERROR:" in native_log:
                native_errors.append("Native client reported an engine error; see desktop.log")
                passed = False
                failure = failure or native_errors[-1]
        result = {
            "passed": passed,
            "scope": "exported-native-browser-self-buffs",
            "url": args.url,
            "database": args.database,
            "requested_skills": requested,
            "checks": checks,
            "samples": samples,
            "failure": failure,
            "browser_errors": browser_errors,
            "native_errors": native_errors,
            "network_errors": network_errors,
        }
        private_write(output / "report.json", redact(json.dumps(result, indent=2)) + "\n")
        for path in (command_path, command_path.with_suffix(".tmp")):
            path.unlink(missing_ok=True)
        for directory in (output / "data", output / "config"):
            shutil.rmtree(directory, ignore_errors=True)
        print("Evidence: " + str(output), flush=True)
        if not passed:
            raise SystemExit(failure or "Mixed exported self-buff checks did not complete")
    print(f"Mixed exported self-buffs: {len(checks)} checks passed")


if __name__ == "__main__":
    main()
