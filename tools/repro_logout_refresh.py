#!/usr/bin/env python3
"""Focused browser-only reproduction of the post-logout reload stall.

Registers a fresh account on the exported Web client, creates a character,
enters the world, logs out through the original system menu, reloads the page,
and then records what the account screen does for two minutes. It writes a
step-by-step report plus screenshots so the failure can be explained from
evidence instead of a single timeout.

Usage:
    .local/venv-dev/bin/python tools/repro_logout_refresh.py \
        --url http://127.0.0.1:8184 \
        --output .local/world-population-r1/acceptance/logout-repro-r1
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import secrets
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8184")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument("--output", required=True)
    parser.add_argument("--settle-seconds", type=float, default=120.0)
    parser.add_argument(
        "--probe-flush-seconds",
        type=float,
        default=0.0,
        help="Before reloading, watch IndexedDB for the deleted session for this long.",
    )
    args = parser.parse_args()

    output = pathlib.Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    events: list[dict] = []
    started = time.monotonic()

    def record(kind: str, **values) -> None:
        row = {"at_ms": int((time.monotonic() - started) * 1000), "event": kind}
        row.update(values)
        events.append(row)
        print("EVENT", json.dumps(row)[:300], flush=True)

    suffix = secrets.token_hex(5)
    username = "repro" + suffix
    email = username + "@example.invalid"
    password = secrets.token_urlsafe(24)
    character = "Repro" + suffix
    protected = [username, email, password, character]

    def redact(text: str) -> str:
        for value in protected:
            text = text.replace(value, "[REDACTED]")
        return re.sub(r"([?&]token=)[^ &]+", r"\1[REDACTED]", text)

    def write_report(status: str, extra: dict | None = None) -> None:
        payload = {
            "status": status,
            "url": args.url,
            "events": events,
            "checks": checks,
            **(extra or {}),
        }
        (output / "report.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    checks: list[str] = []
    browser_errors: list[str] = []

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
        page = context.new_page()
        page.on(
            "console",
            lambda message: (
                browser_errors.append(redact(message.text))
                if message.type == "error"
                and message.text.lstrip().startswith(("ERROR:", "SCRIPT ERROR:", "Uncaught "))
                else None
            ),
        )
        page.on("pageerror", lambda error: browser_errors.append(redact(str(error))))

        def web() -> dict:
            try:
                return page.evaluate("() => JSON.parse(window.mt2Snapshot || '{}')") or {}
            except Exception as error:  # noqa: BLE001 - diagnostics only
                record("snapshot_error", error=redact(str(error)))
                return {}

        def account() -> dict:
            return web().get("account", {})

        def wait(name: str, predicate, timeout: float = 60.0) -> bool:
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
            record("wait_timeout", check=name)
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

        def click(key: str) -> None:
            rectangle = account()["controls"][key]
            page.mouse.click(rectangle[0] + rectangle[2] / 2, rectangle[1] + rectangle[3] / 2)

        def fill(key: str, value: str) -> None:
            click(key)
            wait(
                "entry_focus_is_" + key,
                lambda: account().get("focused_control") == key,
                30,
            )
            page.keyboard.press("Control+a")
            page.keyboard.type(value, delay=50)
            page.evaluate(
                "() => new Promise(resolve => requestAnimationFrame(() => "
                "requestAnimationFrame(resolve)))"
            )
            if key == "character_name":
                wait(
                    "character_name_is_complete_" + key,
                    lambda: account().get("character_name_input") == value,
                    30,
                )

        page.goto(args.url, wait_until="domcontentloaded")
        if not wait(
            "exported_account_screen_boots",
            lambda: bool(account()) and "controls" in account(),
            120,
        ):
            write_report("boot_failed", {"browser_errors": browser_errors})
            browser.close()
            return 1

        # The server row only accepts "Select" once the board has probed the
        # auth service and the database, exactly as the main harness waits.
        wait("original_server_is_available", lambda: account().get("available"), 90)
        click("server_confirm")
        stage("login", "original_login_opens")
        click("register_open")
        stage("register", "registration_opens")
        fill("register_username", username)
        fill("register_email", email)
        fill("register_password", password)
        click("register_submit")
        if not stage("empire", "registration_reaches_empire"):
            write_report("registration_failed", {"browser_errors": browser_errors})
            browser.close()
            return 1
        click("empire_confirm")
        stage("create", "creation_opens")
        fill("character_name", character)
        click("create_submit")
        if not wait(
            "character_creation_confirmed",
            lambda: any(
                str(row.get("name", "")) == character for row in account().get("characters", [])
            ),
            90,
        ):
            write_report("creation_failed", {"browser_errors": browser_errors})
            browser.close()
            return 1
        stage("select", "selection_opens")
        if not wait(
            "character_is_selected",
            lambda: (
                account().get("selected_id")
                and any(
                    str(row.get("name", "")) == character
                    and str(row.get("character_id", "")) == account().get("selected_id")
                    for row in account().get("characters", [])
                )
            ),
            60,
        ):
            write_report("selection_failed", {"browser_errors": browser_errors})
            browser.close()
            return 1
        click("enter")
        if not wait(
            "world_entry_confirms_character",
            lambda: bool(web().get("identity")) and bool(web().get("map_chunks")),
            120,
        ):
            write_report("world_entry_failed", {"browser_errors": browser_errors})
            browser.close()
            return 1
        record("world_ready", identity=web().get("identity"))

        opened = False
        for _attempt in range(3):
            page.bring_to_front()
            page.keyboard.press("Escape")
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if web().get("ui", {}).get("system", {}).get("visible"):
                    opened = True
                    break
                time.sleep(0.1)
            if opened:
                break
        if not opened:
            record("system_menu_failed")
            write_report("system_menu_failed", {"browser_errors": browser_errors})
            browser.close()
            return 1
        checks.append("system_menu_opens_for_logout")
        print("PASS system_menu_opens_for_logout", flush=True)
        center = web()["ui"]["system"]["logout_center"]
        page.mouse.click(*center)
        stage("login", "browser_logout_returns_to_login")
        wait(
            "browser_logout_removes_presence",
            lambda: account().get("account_identity") in ("", None),
            60,
        )
        page.screenshot(path=str(output / "before-reload.png"))
        record("before_reload", account=account(), saved_session=_saved_session_probe(page))

        if args.probe_flush_seconds > 0:
            # The deletion only becomes durable when IDBFS writes /userfs back.
            # Watch the raw IndexedDB view to see when (or whether) that lands.
            flush_samples: list[dict] = []
            deadline = time.monotonic() + args.probe_flush_seconds
            while True:
                probe = _saved_session_probe(page)
                flush_samples.append(
                    {
                        "at_ms": int((time.monotonic() - started) * 1000),
                        "token_present": bool(probe.get("token_present")),
                        "error": probe.get("error") or probe.get("probe_error", ""),
                    }
                )
                if not flush_samples[-1]["token_present"] or time.monotonic() >= deadline:
                    break
                time.sleep(0.1)
            record(
                "flush_probe",
                samples=flush_samples,
                persisted_after_ms=(
                    flush_samples[-1]["at_ms"] - flush_samples[0]["at_ms"]
                    if not flush_samples[-1]["token_present"]
                    else None
                ),
            )

        page.reload(wait_until="domcontentloaded")
        record("reloaded")
        deadline = time.monotonic() + args.settle_seconds
        seen_stages: set[str] = set()
        while time.monotonic() < deadline:
            snapshot = account()
            stage_name = str(snapshot.get("stage", ""))
            if stage_name:
                seen_stages.add(stage_name)
            if stage_name == "server" and not snapshot.get("busy"):
                break
            time.sleep(0.25)
        page.screenshot(path=str(output / "after-reload.png"))
        after = account()
        record(
            "after_reload",
            account=after,
            stages_seen=sorted(seen_stages),
            saved_session=_saved_session_probe(page),
        )
        settled = after.get("stage") == "server" and not after.get("busy")
        checks.append("logout_refresh_has_no_saved_session") if settled else None
        print(("PASS " if settled else "FAIL ") + "logout_refresh_has_no_saved_session")

        browser.close()

    write_report(
        "passed" if settled else "stalled_after_logout_reload",
        {"browser_errors": browser_errors},
    )
    return 0 if settled else 1


def _saved_session_probe(page) -> dict:
    """Inspect the client's persisted-session view without leaking the token."""
    try:
        return page.evaluate(
            """async () => {
                const out = {stores: [], files: [], token_present: false};
                try {
                    const root = await new Promise((resolve, reject) => {
                        const request = indexedDB.open('/userfs');
                        request.onsuccess = event => resolve(event.target.result);
                        request.onerror = event => reject(event.target.error);
                    });
                    out.stores = Array.from(root.objectStoreNames);
                    for (const name of out.stores) {
                        const rows = await new Promise((resolve, reject) => {
                            const tx = root.transaction(name, 'readonly');
                            const store = tx.objectStore(name);
                            const request = store.getAllKeys ? store.getAllKeys() : null;
                            if (!request) { resolve([]); return; }
                            request.onsuccess = event => resolve(event.target.result);
                            request.onerror = event => reject(request.error);
                        });
                        out.files.push(...rows.map(String));
                    }
                    out.files = out.files.slice(0, 100);
                    out.token_present = out.files.some(path => path.includes('.session'));
                } catch (error) {
                    out.error = String(error);
                }
                return out;
            }"""
        )
    except Exception as error:  # noqa: BLE001 - diagnostics only
        return {"probe_error": str(error)}


if __name__ == "__main__":
    sys.exit(main())
