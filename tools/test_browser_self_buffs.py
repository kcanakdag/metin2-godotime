#!/usr/bin/env python3
"""Qualify an exported self-buff through the real browser client and HUD."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from progression_operator import private_json
from test_browser_target import _player
from test_progression_admin import buff_expectation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument("--skill-vnum", type=int, default=3)
    parser.add_argument("--expiry-timeout", type=float, default=180.0)
    args = parser.parse_args()
    if not args.database.startswith("mt2-p2-"):
        parser.error("Use a disposable mt2-p2- database; this replay spends skill points")
    catalog = json.loads(args.catalog.read_text())
    skill = next((row for row in catalog["skills"] if int(row["vnum"]) == args.skill_vnum), None)
    if skill is None or skill.get("handler") != "self_buff_v1":
        parser.error(f"Skill {args.skill_vnum} is not a catalogued self-buff")
    desired_level = 12
    expected = buff_expectation(args.catalog, args.skill_vnum, desired_level, 1)
    expected_cost = int(expected["cost"])
    expected_duration = int(expected["duration_ticks"])
    accounts = private_json(args.fixture, "account fixture")["accounts"]
    if len(accounts) != 2:
        parser.error("The fixture must contain two existing accounts")
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(args.output, 0o700)
    checks: list[str] = []
    samples: dict[str, object] = {}
    errors: list[str] = []
    network_errors: list[str] = []
    retry_after: list[float] = []
    pages: list = []
    passed = False
    failure = ""
    suffix = secrets.token_hex(3)
    names = [f"SbA{suffix}", f"SbB{suffix}"]

    def snapshot(index: int = 0) -> dict:
        return pages[index].evaluate("() => JSON.parse(window.mt2Snapshot || '{}')")

    def command(index: int, action: str, **values: object) -> None:
        pages[index].evaluate(
            "c => window.mt2Command(JSON.stringify(c))", {"action": action, **values}
        )

    def wait(name: str, predicate, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                checks.append(name)
                print("PASS " + name, flush=True)
                return
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

    def redact(value: object) -> str:
        text = str(value)
        for account in accounts:
            for secret in account.values():
                if isinstance(secret, str) and secret:
                    text = text.replace(secret, "[redacted]")
        return text

    def panel() -> dict:
        return snapshot().get("ui", {}).get("skills", {})

    def skill_row(vnum: int) -> dict:
        return next((row for row in panel().get("rows", []) if int(row["skill_vnum"]) == vnum), {})

    def control(vnum: int) -> dict:
        return next(row for row in panel()["controls"] if int(row["vnum"]) == vnum)

    def reveal(vnum: int) -> dict:
        if not panel().get("visible"):
            pages[0].keyboard.press("k")
            wait("skill_panel_open", lambda: panel().get("visible"))
        for _ in range(30):
            entry = control(vnum)
            if entry["fully_visible"]:
                return entry
            state = panel()
            point = state["scroll_center"]
            delta = entry["slot_center"][1] - point[1]
            pages[0].mouse.move(*point)
            pages[0].mouse.wheel(0, max(-1000.0, min(1000.0, delta)))
            time.sleep(0.2)
        raise AssertionError("Skill control is not accessible: " + str(vnum))

    def progression(identity: str, index: int = 0) -> dict:
        return next(
            (
                row
                for row in snapshot(index).get("progression", [])
                if row.get("character_id") == identity
            ),
            {},
        )

    def owner_buff(index: int = 0) -> dict:
        identity = snapshot(0)["identity"]
        return next(
            (
                row
                for row in snapshot(index).get("buffs", [])
                if row.get("character_id") == identity
                and int(row.get("skill_vnum", 0)) == args.skill_vnum
                and not bool(row.get("paused", True))
            ),
            {},
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
        try:
            character_ids: list[str] = []
            for index, account in enumerate(accounts):
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    record_video_dir=str(args.output / "videos"),
                    record_video_size={"width": 1280, "height": 800},
                )
                context.add_init_script("window.mt2ProbeEnabled = true;")
                page = context.new_page()
                pages.append(page)
                page.on("pageerror", lambda error: errors.append(redact(error)))
                page.on(
                    "console",
                    lambda msg: (
                        errors.append(redact(msg.text))
                        if msg.type == "error"
                        and msg.text.lstrip().startswith(("ERROR:", "SCRIPT ERROR:"))
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
                    f"client_{index}_boots",
                    lambda index=index: bool(snapshot(index).get("account")),
                    90,
                )
                assert snapshot(index)["database"] == args.database
                for attempt in range(4):
                    retry_after.clear()
                    command(
                        index,
                        "login",
                        username=account["username"],
                        password=account["password"],
                    )
                    if wait_state(
                        lambda index=index: snapshot(index).get("connection_state") == "lobby",
                        60,
                    ):
                        checks.append(f"client_{index}_lobby")
                        print(f"PASS client_{index}_lobby", flush=True)
                        break
                    if attempt == 3 or not retry_after:
                        raise AssertionError(f"client_{index}_lobby timed out")
                    delay = min(max(retry_after) + 2.0, 75.0)
                    print(
                        f"RETRY client_{index}_lobby after {delay:.0f}s auth rate limit",
                        flush=True,
                    )
                    time.sleep(delay)
                used_slots = {
                    int(row.get("slot", -1))
                    for row in snapshot(index)["account"].get("characters", [])
                }
                free_slots = [slot for slot in range(4) if slot not in used_slots]
                if not free_slots:
                    raise AssertionError(f"client_{index} has no free character slot")
                command(index, "create", slot=free_slots[0], name=names[index])
                wait(
                    f"client_{index}_character_created",
                    lambda index=index, name=names[index]: any(
                        row.get("name") == name
                        for row in snapshot(index)["account"].get("characters", [])
                    ),
                )
                character_id = next(
                    row["character_id"]
                    for row in snapshot(index)["account"]["characters"]
                    if row["name"] == names[index]
                )
                character_ids.append(character_id)
                command(index, "select", character_id=character_id)
                wait(
                    f"client_{index}_character_selected",
                    lambda index=index, character_id=character_id: (
                        snapshot(index)["account"].get("selected_id") == character_id
                    ),
                )
                command(index, "enter")
                wait(
                    f"client_{index}_enters_world",
                    lambda index=index: snapshot(index).get("connection_state") == "connected",
                    120,
                )
            owner = snapshot(0)["identity"]
            peer = snapshot(1)["identity"]
            assert owner != peer
            wait(
                "independent_rendered_peers",
                lambda: all(
                    any(row["identity"] == identity for row in snapshot(index)["rendered_actors"])
                    for index, identity in [(0, peer), (1, owner)]
                ),
            )
            pages[0].keyboard.press("Enter")
            wait("admin_setup_chat_focus", lambda: snapshot()["ui"]["chat"]["focused"])
            pages[0].keyboard.type(f"/level {desired_level}")
            pages[0].keyboard.press("Enter")
            wait(
                "authorized_level_setup",
                lambda: int(progression(owner).get("level", 0)) >= desired_level,
            )
            entry = reveal(args.skill_vnum)
            assert entry["learn_enabled"], "No authorized skill point available"
            pages[0].mouse.click(*entry["learn_center"])
            wait(
                "self_buff_rank_subscribed",
                lambda: int(skill_row(args.skill_vnum).get("rank", 0)) == 1,
            )
            entry = reveal(args.skill_vnum)
            destination = snapshot()["ui"]["quickslot_centers"][0]
            pages[0].mouse.move(*entry["slot_center"])
            pages[0].mouse.down()
            pages[0].mouse.move(entry["slot_center"][0] + 20, entry["slot_center"][1], steps=4)
            pages[0].mouse.move(*destination, steps=12)
            pages[0].mouse.up()
            wait(
                "self_buff_quickslot_bound",
                lambda: snapshot()["ui"]["quickslot_skill_bindings"][0] == args.skill_vnum,
            )
            pages[0].screenshot(path=str(args.output / "self-buff-learned.png"))
            pages[0].keyboard.press("Escape")
            wait("skill_panel_closed", lambda: not panel().get("visible"))
            before_sp = int(progression(owner).get("current_sp", -1))
            before_ready = int(skill_row(args.skill_vnum).get("ready_at_us", 0))
            before_sequences = [
                int(_player(snapshot(index), owner).get("attack_sequence", 0)) for index in [0, 1]
            ]
            assert before_sp >= expected_cost, "Insufficient SP for the rank-one cast"
            pages[0].keyboard.press("1")
            wait(
                "self_buff_action_replicates",
                lambda: all(
                    int(_player(snapshot(index), owner).get("attack_sequence", 0))
                    > before_sequences[index]
                    and str(_player(snapshot(index), owner).get("attack_action_id", "")).endswith(
                        f".skill_{args.skill_vnum}"
                    )
                    for index in [0, 1]
                ),
            )
            wait(
                "self_buff_status_owner_only",
                lambda: bool(owner_buff()) and not snapshot(1).get("buffs"),
            )
            wait(
                "self_buff_sp_paid_once",
                lambda: int(progression(owner).get("current_sp", -1)) == before_sp - expected_cost,
            )
            wait(
                "self_buff_hud_icon",
                lambda: (
                    int(snapshot()["ui"]["buffs"]["count"]) == 1
                    and snapshot()["ui"]["buffs"]["rows"][0]["name"] == skill["name"]
                    and int(snapshot(1)["ui"]["buffs"]["count"]) == 0
                ),
            )
            wait(
                "self_buff_cooldown_started",
                lambda: int(skill_row(args.skill_vnum).get("ready_at_us", 0)) > before_ready,
            )
            first = owner_buff()
            first_remaining = int(first["remaining_ticks"])
            first_id = str(first["id"])
            assert expected_duration - 1 <= first_remaining <= expected_duration, (
                f"Unexpected rank-one duration {first_remaining} ticks; "
                f"catalog expects {expected_duration}"
            )
            paid_sp = int(progression(owner).get("current_sp", -1))
            paid_ready = int(skill_row(args.skill_vnum).get("ready_at_us", 0))
            paid_sequences = [
                int(_player(snapshot(index), owner).get("attack_sequence", 0)) for index in [0, 1]
            ]
            pages[0].screenshot(path=str(args.output / "self-buff-cast.png"))
            pages[0].keyboard.press("1")
            time.sleep(1.0)
            assert int(progression(owner).get("current_sp", -1)) == paid_sp, (
                "Cooling cast paid SP twice"
            )
            assert int(skill_row(args.skill_vnum).get("ready_at_us", 0)) == paid_ready, (
                "Cooling cast moved the cooldown"
            )
            assert [
                int(_player(snapshot(index), owner).get("attack_sequence", 0)) for index in [0, 1]
            ] == paid_sequences, "Cooling cast replicated a second action"
            checks.append("cooling_cast_rejected_without_payment")
            print("PASS cooling_cast_rejected_without_payment", flush=True)
            wait(
                "self_buff_duration_updates",
                lambda: (
                    bool(owner_buff()) and int(owner_buff()["remaining_ticks"]) < first_remaining
                ),
                15,
            )
            before_reconnect = owner_buff()
            pages[0].screenshot(path=str(args.output / "self-buff-before-reconnect.png"))
            command(0, "disconnect")
            wait(
                "owner_disconnected",
                lambda: snapshot().get("connection_state") == "disconnected",
                30,
            )
            command(0, "reconnect")
            wait(
                "reconnect_returns_to_lobby",
                lambda: snapshot().get("connection_state") in {"lobby", "connected"},
                60,
            )
            if snapshot().get("connection_state") == "lobby":
                command(0, "select", character_id=character_ids[0])
                wait(
                    "reconnect_reselects_character",
                    lambda: snapshot()["account"].get("selected_id") == character_ids[0],
                )
                command(0, "enter")
            wait(
                "reconnect_returns_to_world",
                lambda: snapshot().get("connection_state") == "connected",
                120,
            )
            wait(
                "reconnect_restores_owner_status",
                lambda: (
                    bool(owner_buff())
                    and str(owner_buff()["id"]) == first_id
                    and int(snapshot()["ui"]["buffs"]["count"]) == 1
                    and not snapshot(1).get("buffs")
                ),
                30,
            )
            restored = owner_buff()
            assert int(restored["remaining_ticks"]) <= int(before_reconnect["remaining_ticks"]), (
                "Reconnect replayed the full duration"
            )
            assert int(progression(owner).get("current_sp", -1)) == paid_sp, (
                "Reconnect replayed SP payment"
            )
            checks.append("reconnect_does_not_replay_payment")
            print("PASS reconnect_does_not_replay_payment", flush=True)
            pages[0].screenshot(path=str(args.output / "self-buff-after-reconnect.png"))
            samples["cast"] = {
                "skill_vnum": args.skill_vnum,
                "skill_name": skill["name"],
                "expected_rank_one_cost": expected_cost,
                "expected_rank_one_duration": expected_duration,
                "sp_before": before_sp,
                "sp_after": paid_sp,
                "remaining_ticks_first": first_remaining,
                "buff_id": first_id,
                "before_sequences": before_sequences,
                "paid_sequences": paid_sequences,
            }
            wait(
                "self_buff_expires",
                lambda: not owner_buff() and int(snapshot()["ui"]["buffs"]["count"]) == 0,
                args.expiry_timeout,
            )
            assert not snapshot(1).get("buffs"), "Peer retained owner-only buff status"
            checks.append("expiry_preserves_peer_isolation")
            print("PASS expiry_preserves_peer_isolation", flush=True)
            assert int(progression(owner).get("current_sp", -1)) == paid_sp, (
                "Expiry replayed SP payment"
            )
            checks.append("expiry_does_not_replay_payment")
            print("PASS expiry_does_not_replay_payment", flush=True)
            pages[0].screenshot(path=str(args.output / "self-buff-expired.png"))
            assert not errors, "Browser engine errors: " + "; ".join(errors[:3])
            checks.append("no_browser_engine_errors")
            passed = True
        except Exception as error:
            failure = redact(error) or type(error).__name__
            samples["failure_clients"] = []
            for index in range(len(pages)):
                try:
                    state = snapshot(index)
                    samples["failure_clients"].append(
                        {
                            key: state.get(key)
                            for key in (
                                "connection_state",
                                "fps",
                                "snapshot_age_ms",
                                "account",
                                "buffs",
                                "command_feedback",
                                "connection_message",
                                "content_error",
                                "npc_error",
                                "progression",
                                "projectile_error",
                                "skill_effect_error",
                                "target_effect_error",
                                "world_entry_error",
                            )
                        }
                        | {
                            "body_text": pages[index].locator("body").inner_text(),
                            "notice": state.get("ui", {}).get("notice", ""),
                        }
                    )
                except Exception as diagnostic_error:
                    samples["failure_clients"].append({"error": redact(diagnostic_error)})
            if pages:
                pages[0].screenshot(path=str(args.output / "failure.png"))
        finally:
            for context in browser.contexts:
                context.close()
            browser.close()
            report = {
                "scope": "exported-self-buff-controls",
                "database": args.database,
                "skill_vnum": args.skill_vnum,
                "skill_name": skill["name"],
                "passed": passed,
                "checks": checks,
                "samples": samples,
                "failure": failure,
                "browser_errors": errors,
                "network_errors": network_errors,
            }
            (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if not passed:
        raise SystemExit(failure)
    print(f"Exported self-buff controls: {len(checks)} checks passed")


if __name__ == "__main__":
    main()
