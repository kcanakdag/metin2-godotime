#!/usr/bin/env python3
"""Focused browser reproduction of a silently ignored login submit.

The acceptance replay failed `wrong_password_remains_on_original_login`: the
original login screen kept `stage=login`, `busy=false` and an empty message for
the whole wait after the submit button was clicked with rejected credentials.
A player-visible message is the expected outcome, so this tool replays only that
step and records a fine-grained timeline plus the browser-level pointer events
that reached the canvas. That separates three otherwise identical reports:

* the browser never delivered the click,
* the engine swallowed it (control disabled at that instant), or
* the transport dropped the attempt without telling the player.

Usage:
    .local/venv-dev/bin/python tools/repro_login_rejection.py \
        --url http://127.0.0.1:8184 \
        --output .local/world-population-r1/acceptance/login-rejection-r1

The auth service limits sign-in attempts per window (5 per minute by default),
so keep `--attempts` small.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import secrets
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Runs before any page script. Capture the pointer events the browser actually
# dispatches to the canvas so a missing message can be attributed to the click
# delivery instead of guessed from a frozen snapshot.
CANVAS_INPUT_AUDIT = """(() => {
    const audit = window.mt2InputAudit = {events: []};
    const append = (row) => {
        if (audit.events.length < 400) audit.events.push(row);
    };
    for (const type of ["pointerdown", "pointerup", "mousedown", "mouseup", "click"]) {
        window.addEventListener(type, (event) => {
            const canvas = event.target instanceof HTMLCanvasElement;
            append({
                at_ms: Date.now(),
                type: type,
                canvas: canvas,
                target: event.target ? event.target.tagName : "",
                x: event.clientX,
                y: event.clientY,
                buttons: event.buttons
            });
            if (canvas) {
                const key = "focusBefore" + type;
                audit[key] = document.hasFocus();
            }
        }, true);
    }
})();"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8184")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument("--output", required=True)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--feedback-seconds", type=float, default=25.0)
    parser.add_argument("--boot-seconds", type=float, default=120.0)
    args = parser.parse_args()

    output = pathlib.Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    started = time.monotonic()
    checks: list[str] = []
    browser_errors: list[str] = []
    attempts: list[dict] = []

    def at_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    def write_report(status: str, extra: dict | None = None) -> None:
        payload = {
            "status": status,
            "url": args.url,
            "checks": checks,
            "attempts": attempts,
            "browser_errors": browser_errors,
            **(extra or {}),
        }
        (output / "report.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=args.chrome,
            headless=True,
            args=[
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        context.add_init_script("window.mt2ProbeEnabled = true;")
        context.add_init_script(CANVAS_INPUT_AUDIT)
        page = context.new_page()
        page.on(
            "console",
            lambda message: (
                browser_errors.append(message.text)
                if message.type == "error"
                and message.text.lstrip().startswith(("ERROR:", "SCRIPT ERROR:", "Uncaught "))
                else None
            ),
        )
        page.on("pageerror", lambda error: browser_errors.append(str(error)))

        def web() -> dict:
            try:
                return page.evaluate("() => JSON.parse(window.mt2Snapshot || '{}')") or {}
            except Exception:  # noqa: BLE001 - diagnostics only
                return {}

        def account() -> dict:
            return web().get("account", {})

        def wait(name: str, predicate, timeout: float) -> bool:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    if predicate():
                        checks.append(name)
                        print("PASS", name, flush=True)
                        return True
                except Exception:  # noqa: BLE001 - keep polling a transient state
                    pass
                time.sleep(0.1)
            print("FAIL", name, flush=True)
            return False

        def stage(name: str, check: str, timeout: float = 60.0) -> bool:
            return wait(
                check,
                lambda: (
                    account().get("visible")
                    and account().get("stage") == name
                    and not account().get("busy")
                ),
                timeout,
            )

        def rectangle(key: str) -> list[float]:
            return account()["controls"][key]

        def click(key: str) -> None:
            rect = rectangle(key)
            page.mouse.click(rect[0] + rect[2] / 2, rect[1] + rect[3] / 2)

        def fill(key: str, value: str, timeout: float = 30.0) -> bool:
            click(key)
            if not wait(
                "entry_focus_is_" + key, lambda: account().get("focused_control") == key, timeout
            ):
                return False
            page.keyboard.press("Control+a")
            page.keyboard.type(value, delay=50)
            page.evaluate(
                "() => new Promise(resolve => requestAnimationFrame(() => "
                "requestAnimationFrame(resolve)))"
            )
            return True

        def sample(timeline: list[dict], label: str) -> dict:
            snapshot = web()
            entry = snapshot.get("account", {})
            row = {
                "at_ms": at_ms(),
                "label": label,
                "snapshot_seq": snapshot.get("snapshot_seq"),
                "published_at_ms": snapshot.get("snapshot_published_at_ms"),
                "fps": snapshot.get("fps"),
                "connection_state": snapshot.get("connection_state"),
                "stage": entry.get("stage"),
                "busy": entry.get("busy"),
                "available": entry.get("available"),
                "focused_control": entry.get("focused_control"),
                "message": entry.get("message"),
                "login_submit": (entry.get("controls") or {}).get("login_submit"),
                "mouse_position": snapshot.get("mouse_position"),
                "hovered_control": snapshot.get("hovered_control"),
            }
            timeline.append(row)
            print("SAMPLE", json.dumps(row)[:280], flush=True)
            return row

        page.goto(args.url, wait_until="domcontentloaded")
        if not wait(
            "exported_account_screen_boots",
            lambda: bool(account()) and "controls" in account(),
            args.boot_seconds,
        ):
            write_report("boot_failed")
            browser.close()
            return 1
        if not wait("original_server_is_available", lambda: account().get("available"), 90):
            write_report("server_unavailable")
            browser.close()
            return 1
        click("server_confirm")
        if not stage("login", "original_login_opens"):
            write_report("login_unreachable")
            browser.close()
            return 1

        for attempt in range(1, args.attempts + 1):
            timeline: list[dict] = []
            username = "repro" + secrets.token_hex(4)
            wrong = "incorrect-" + secrets.token_hex(6)
            result: dict = {"attempt": attempt, "username": username}
            if not fill("username", username):
                result["outcome"] = "username_focus_failed"
                attempts.append(result)
                break
            if not fill("password", wrong):
                result["outcome"] = "password_focus_failed"
                attempts.append(result)
                break
            before = sample(timeline, "before_submit")
            page.evaluate("() => { window.mt2InputAudit.events.length = 0; }")
            click("login_submit")
            result["click_at_ms"] = at_ms()
            result["click_target"] = before.get("login_submit")

            deadline = time.monotonic() + args.feedback_seconds
            outcome = "silent_no_op"
            while time.monotonic() < deadline:
                time.sleep(0.25)
                row = sample(timeline, "poll")
                message = str(row.get("message", ""))
                if "incorrect" in message.lower():
                    outcome = "feedback"
                    break
                if row.get("stage") != "login":
                    outcome = "left_login"
                    break
            result["outcome"] = outcome
            result["final"] = timeline[-1] if timeline else {}
            result["input_audit"] = page.evaluate(
                "() => (window.mt2InputAudit ? window.mt2InputAudit.events : [])"
            )
            result["retained_password_field_mask"] = account().get("password_masked")
            result["timeline"] = timeline
            attempts.append(result)
            page.screenshot(path=str(output / f"attempt-{attempt}-{outcome}.png"))
            print("ATTEMPT", attempt, outcome, json.dumps(result["input_audit"])[:200], flush=True)
            if outcome != "feedback":
                break
            if not stage("login", f"login_screen_stays_after_rejection_{attempt}", 30):
                break

        passed = bool(attempts) and all(row.get("outcome") == "feedback" for row in attempts)
        write_report("passed" if passed else "failed")
        browser.close()
        return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
