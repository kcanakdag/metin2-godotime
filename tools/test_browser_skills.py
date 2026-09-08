#!/usr/bin/env python3
"""Focused exported skill controls using two existing, isolated development accounts."""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from progression_operator import private_json
from test_browser_target import _pick, _player


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument("--skills", type=int, nargs="+", default=[16, 17])
    args = parser.parse_args()
    if not args.database.startswith("mt2-p2-"):
        parser.error(
            "Use a disposable mt2-p2- database; this replay spends development skill points"
        )
    if not args.skills or len(set(args.skills)) != len(args.skills):
        parser.error("Select distinct skills")
    accounts = private_json(args.fixture, "account fixture")["accounts"]
    if len(accounts) != 2:
        parser.error("The fixture must contain two existing accounts")
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(args.output, 0o700)
    checks, samples, errors = [], {}, []
    passed, failure = False, ""
    pages = []

    def snapshot(index=0):
        return pages[index].evaluate("() => JSON.parse(window.mt2Snapshot || '{}')")

    def command(index, action, **values):
        pages[index].evaluate(
            "c => window.mt2Command(JSON.stringify(c))", {"action": action, **values}
        )

    def wait(name, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                checks.append(name)
                print("PASS " + name, flush=True)
                return
            time.sleep(0.05)
        raise AssertionError(name + " timed out")

    def panel():
        return snapshot().get("ui", {}).get("skills", {})

    def skill_row(vnum):
        return next((r for r in panel().get("rows", []) if r["skill_vnum"] == vnum), {})

    def control(vnum):
        return next(c for c in panel()["controls"] if c["vnum"] == vnum)

    def reveal(vnum):
        if not panel().get("visible"):
            pages[0].keyboard.press("k")
            wait("skill_panel_open", lambda: panel().get("visible"))
        point = panel()["scroll_center"]
        pages[0].mouse.move(*point)
        pages[0].mouse.wheel(0, -1000)
        time.sleep(0.15)
        for _ in range(8):
            if control(vnum)["fully_visible"]:
                return control(vnum)
            pages[0].mouse.wheel(0, 60)
            time.sleep(0.15)
        raise AssertionError("Skill control is not accessible: " + str(vnum))

    def dummy(index):
        return next(r for r in snapshot(index)["monsters"] if r["id"] == 900001)

    def redact(value):
        for account in accounts:
            for secret in account.values():
                if isinstance(secret, str) and secret:
                    value = value.replace(secret, "[redacted]")
        return value

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=args.chrome,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--enable-gpu"],
        )
        try:
            for index, account in enumerate(accounts):
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                context.add_init_script("window.mt2ProbeEnabled = true;")
                page = context.new_page()
                pages.append(page)
                page.on("pageerror", lambda error: errors.append(redact(str(error))))
                page.on(
                    "console",
                    lambda msg: (
                        errors.append(redact(msg.text))
                        if msg.type == "error"
                        and msg.text.lstrip().startswith(("ERROR:", "SCRIPT ERROR:"))
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
                command(index, "login", username=account["username"], password=account["password"])
                wait(
                    f"client_{index}_existing_roster",
                    lambda index=index: snapshot(index).get("connection_state") == "lobby",
                )
                command(index, "enter")
                wait(
                    f"client_{index}_enters",
                    lambda index=index: snapshot(index).get("connection_state") == "connected",
                    120,
                )
            samples["renderers"] = [
                page.evaluate("""() => {
                const gl = document.querySelector('canvas').getContext('webgl2');
                const debug = gl && gl.getExtension('WEBGL_debug_renderer_info');
                return debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : 'unavailable';
            }""")
                for page in pages
            ]
            owner = snapshot()["identity"]
            peer = snapshot(1)["identity"]
            assert owner != peer
            wait(
                "independent_rendered_peers",
                lambda: all(
                    any(r["identity"] == identity for r in snapshot(index)["rendered_actors"])
                    for index, identity in [(0, peer), (1, owner)]
                ),
            )
            rows = panel()["rows"]
            desired_level = max(8, 4 + sum(int(r["points_spent"]) for r in rows) + len(args.skills))
            pages[0].keyboard.press("Enter")
            wait("admin_setup_chat_focus", lambda: snapshot()["ui"]["chat"]["focused"])
            pages[0].keyboard.type(f"/level {desired_level}")
            pages[0].keyboard.press("Enter")
            wait(
                "authorized_level_setup",
                lambda: any(
                    r["character_id"] == owner and int(r["level"]) >= desired_level
                    for r in snapshot()["progression"]
                ),
            )
            for slot_index, vnum in enumerate(args.skills):
                before_rank = int(skill_row(vnum).get("rank", 0))
                entry = reveal(vnum)
                assert entry["learn_enabled"], "No authorized point available"
                pages[0].mouse.click(*entry["learn_center"])
                wait(
                    f"skill_{vnum}_rank_subscribed",
                    lambda vnum=vnum, before_rank=before_rank: (
                        int(skill_row(vnum).get("rank", 0)) == before_rank + 1
                    ),
                )
                entry = reveal(vnum)
                destination = snapshot()["ui"]["quickslot_centers"][slot_index]
                pages[0].mouse.move(*entry["slot_center"])
                pages[0].mouse.down()
                pages[0].mouse.move(entry["slot_center"][0] + 20, entry["slot_center"][1], steps=4)
                pages[0].mouse.move(*destination, steps=12)
                pages[0].mouse.up()
                wait(
                    f"skill_{vnum}_quickslot_bound",
                    lambda slot_index=slot_index, vnum=vnum: (
                        snapshot()["ui"]["quickslot_skill_bindings"][slot_index] == vnum
                    ),
                )
                pages[0].screenshot(path=str(args.output / f"skill-{vnum}-learned.png"))
                pages[0].keyboard.press("Escape")
                wait("skill_panel_closed", lambda: not panel()["visible"])
                target = dummy(0)
                for offset in [-2.7, -2.0]:
                    destination = [target["x"] + offset, target["z"]]
                    command(0, "target", x=destination[0], z=destination[1])
                    wait(
                        f"skill_{vnum}_approach_{offset}",
                        lambda destination=destination: (
                            math.dist(
                                [
                                    _player(snapshot(1), owner).get("x", 1e6),
                                    _player(snapshot(1), owner).get("z", 1e6),
                                ],
                                destination,
                            )
                            < 0.1
                        ),
                    )
                command(0, "stop")
                wait(
                    "dummy_has_pointer_projection",
                    lambda target=target: (
                        _pick(snapshot(), 900001, target["life_sequence"]) is not None
                    ),
                )
                pages[0].mouse.click(*_pick(snapshot(), 900001, target["life_sequence"]))
                wait(
                    "pointer_selects_dummy",
                    lambda: snapshot()["combat_target"].get("target_id") == 900001,
                )
                before = int(dummy(0)["health"])
                ready = int(skill_row(vnum).get("ready_at_us", 0))
                sequences = [
                    int(_player(snapshot(index), owner)["attack_sequence"]) for index in [0, 1]
                ]
                pages[0].keyboard.press(str(slot_index + 1))
                wait(
                    f"skill_{vnum}_server_cooldown",
                    lambda vnum=vnum, ready=ready: (
                        int(skill_row(vnum).get("ready_at_us", 0)) > ready
                    ),
                )
                wait(
                    f"skill_{vnum}_action_replicates",
                    lambda vnum=vnum, sequences=sequences: all(
                        int(_player(snapshot(index), owner)["attack_sequence"]) > sequences[index]
                        and str(
                            _player(snapshot(index), owner).get("attack_action_id", "")
                        ).endswith(f".skill_{vnum}")
                        for index in [0, 1]
                    ),
                )
                wait(
                    f"skill_{vnum}_damage_replicates",
                    lambda before=before: (
                        int(dummy(0)["health"]) < before
                        and dummy(0)["health"] == dummy(1)["health"]
                    ),
                )
                samples[str(vnum)] = {
                    "rank": int(skill_row(vnum)["rank"]),
                    "attack_sequences_before": sequences,
                    "attack_sequences_after": [
                        int(_player(snapshot(index), owner)["attack_sequence"]) for index in [0, 1]
                    ],
                    "health": [before, int(dummy(0)["health"])],
                    "life": target["life_sequence"],
                }
                assert (
                    dummy(0)["life_sequence"]
                    == dummy(1)["life_sequence"]
                    == target["life_sequence"]
                )
                pages[0].screenshot(path=str(args.output / f"skill-{vnum}-cast.png"))
                time.sleep(2)
            assert not errors, "Browser engine errors: " + "; ".join(errors[:3])
            checks.append("no_browser_engine_errors")
            passed = True
        except Exception as error:
            failure = redact(str(error)) or type(error).__name__
            if pages:
                pages[0].screenshot(path=str(args.output / "failure.png"))
        finally:
            browser.close()
            report = {
                "scope": "exported-skill-controls",
                "database": args.database,
                "skills": args.skills,
                "passed": passed,
                "checks": checks,
                "samples": samples,
                "failure": failure,
                "browser_errors": errors,
            }
            (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if not passed:
        raise SystemExit(failure)
    print(f"Exported skill controls: {len(checks)} checks passed")


if __name__ == "__main__":
    main()
