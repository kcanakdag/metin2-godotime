#!/usr/bin/env python3
"""Verify original account entry in exported Web/Linux clients on one actual server.

Requires --test-probe exports. Browser entry uses visible canvas controls; native
commands are limited to ordinary validated actions. No database queries or tokens.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from test_browser import distance
from test_browser_inventory import exercise_inventory
from test_browser_panels import exercise_panels

ROOT = Path(__file__).resolve().parents[1]


def private_write(path: Path, text: str) -> None:
    """Create command/log files with owner-only access from their first byte."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as destination:
        os.chmod(path, 0o600)
        destination.write(text)


def seen(snapshot: dict, identity: str):
    return next(
        (
            actor["position"]
            for actor in snapshot.get("rendered_actors", [])
            if actor["identity"] == identity
        ),
        None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://kcanakdag.com:8443")
    parser.add_argument("--database", default="mt2-browser-proof")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument("--hardware", action="store_true", help="Visible Chrome with system GPU")
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--panels", action="store_true")
    parser.add_argument(
        "--session-refresh",
        action="store_true",
        help="Wait for both real four-minute session refresh timers while in world",
    )
    parser.add_argument("--native", type=Path, default=ROOT / "dist/linux-test/MT2Spacetime.x86_64")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.native.is_file():
        parser.error("Missing exported Linux test client; export with --test-probe first.")
    if not shutil.which("xvfb-run"):
        parser.error("The native client requires xvfb-run.")
    output = args.output or ROOT / ".local/browser-accounts" / time.strftime("%Y%m%d-%H%M%S")
    output = output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(output, 0o700)
    report_path, command_path = output / "desktop.json", output / "commands.json"
    suffix = secrets.token_hex(5)
    credentials = {
        side: {
            "username": side + suffix,
            "email": side + suffix + "@example.invalid",
            "password": secrets.token_urlsafe(24),
        }
        for side in ("web", "native")
    }
    names = {"web": "Web" + suffix, "native": "Desk" + suffix, "second": "Alt" + suffix}
    protected = [value for credential in credentials.values() for value in credential.values()]
    checks: list[str] = []
    samples: dict = {}
    browser_errors: list[str] = []
    sequence = 0
    page = None
    process = None
    passed = False
    failure = ""
    started = time.monotonic()

    def redact(text: str) -> str:
        for value in protected:
            text = text.replace(value, "[REDACTED]")
        return re.sub(r"([?&]token=)[^ &]+", r"\1[REDACTED]", text)

    def desktop() -> dict:
        try:
            return json.loads(report_path.read_text())
        except (OSError, ValueError):
            return {}

    def native_command(action: str, **values) -> None:
        nonlocal sequence
        sequence += 1
        temporary = command_path.with_suffix(".tmp")
        private_write(temporary, json.dumps({"sequence": sequence, "action": action, **values}))
        temporary.replace(command_path)

    def web() -> dict:
        return page.evaluate("() => JSON.parse(window.mt2Snapshot || '{}')")

    def account(snapshot=None) -> dict:
        return (web() if snapshot is None else snapshot).get("account", {})

    def web_command(action: str, **values) -> None:
        page.evaluate("c => window.mt2Command(JSON.stringify(c))", {"action": action, **values})

    def wait(name, predicate, timeout=30) -> None:
        deadline = time.monotonic() + timeout
        last_notice = time.monotonic()
        while time.monotonic() < deadline:
            if predicate():
                checks.append(name)
                print("PASS " + name, flush=True)
                return
            if process is not None and process.poll() is not None:
                raise AssertionError("Exported native client exited during " + name)
            if timeout > 90 and time.monotonic() - last_notice >= 30:
                print("WAIT " + name, flush=True)
                last_notice = time.monotonic()
            time.sleep(0.1)
        if page is not None and not page.is_closed():
            samples["failed_web"] = web()
            page.screenshot(path=str(output / "failure.png"))
        raise AssertionError(name + " timed out")

    def stage(name: str, check: str, timeout: float = 30) -> None:
        wait(
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
        wait("entry_focus_is_" + key, lambda: account().get("focused_control") == key)
        page.keyboard.press("Control+a")
        page.keyboard.type(value, delay=50)
        page.evaluate(
            "() => new Promise(resolve => requestAnimationFrame(() => "
            "requestAnimationFrame(resolve)))"
        )
        if key == "character_name":
            wait(
                "character_name_is_complete_before_submit",
                lambda: (
                    account().get("character_name_input") == value
                    and account().get("focused_control") == key
                ),
            )

    def selected(snapshot: dict, name: str) -> str:
        return next(
            (
                row["character_id"]
                for row in account(snapshot).get("characters", [])
                if row["name"] == name
            ),
            "",
        )

    def selection_ready(name: str) -> bool:
        snapshot = web()
        character_id = selected(snapshot, name)
        return (
            bool(character_id)
            and account(snapshot).get("stage") == "select"
            and account(snapshot).get("selected_id") == character_id
            and not account(snapshot).get("busy")
        )

    def system_action(action: str) -> None:
        page.keyboard.press("Escape")
        wait(
            "system_menu_opens_for_" + action,
            lambda: web().get("ui", {}).get("system", {}).get("visible"),
        )
        center = web()["ui"]["system"][action + "_center"]
        viewport = page.viewport_size
        assert 0 <= center[0] < viewport["width"] and 0 <= center[1] < viewport["height"], (
            "Original system-menu control is outside the viewport: " + action
        )
        page.mouse.click(*center)

    def settle(identity: str, check: str) -> list:
        web_command("stop")
        wait(
            check,
            lambda: (
                web().get("activity") == 0
                and any(
                    row["identity"] == identity and row["activity"] == 0
                    for row in desktop().get("player_rows", [])
                )
                and distance(seen(desktop(), identity), web().get("server_position")) < 0.02
            ),
        )
        return web()["server_position"]

    private_write(output / "desktop.log", "")
    log = (output / "desktop.log").open("w")
    try:
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
                headless=not args.hardware,
                args=[]
                if args.hardware
                else [
                    "--use-angle=swiftshader",
                    "--enable-unsafe-swiftshader",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(viewport={"width": 1280, "height": 800})
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
            page.goto(args.url, wait_until="domcontentloaded")
            wait(
                "both_exported_account_screens_boot",
                lambda: bool(account()) and bool(account(desktop())),
                90,
            )
            if args.session_refresh:
                assert "connected_at_msec" in web() and "connected_at_msec" in desktop(), (
                    "Session-refresh proof requires exports with connected_at_msec snapshots"
                )
            assert "focused_control" in account() and "character_name_input" in account(), (
                "Account input proof requires exports with the current intro focus snapshots"
            )
            assert web()["database"] == desktop()["database"] == args.database, (
                "Both exports must target the requested database"
            )
            checks.append("both_exports_target_requested_database")
            wait(
                "original_server_is_available",
                lambda: account().get("available") and account(desktop()).get("available"),
            )
            samples["engine_ready_seconds"] = round(time.monotonic() - started, 2)
            page.screenshot(path=str(output / "account-server.png"))
            native_command("register", **credentials["native"])
            click("server_confirm")
            stage("login", "original_login_opens")
            page.screenshot(path=str(output / "account-login.png"))
            click("register_open")
            stage("register", "registration_opens")
            for key, field in [
                ("username", "register_username"),
                ("email", "register_email"),
                ("password", "register_password"),
            ]:
                fill(field, credentials["web"][key])
            assert account()["password_masked"]
            checks.append("registration_password_is_masked")
            click("register_submit")
            stage("empire", "browser_registration_reaches_original_empire")
            assert account()["roster_count"] == 0 and not web()["rendered_actors"]
            checks.append("new_account_has_no_invented_character")
            page.screenshot(path=str(output / "account-empire.png"))
            wait(
                "native_registration_creates_empty_lobby",
                lambda: (
                    desktop().get("connection_state") == "lobby"
                    and account(desktop()).get("roster_count") == 0
                ),
            )
            native_command("create", slot=0, name=names["native"])
            click("empire_confirm")
            stage("create", "supported_empire_opens_original_creation")
            fill("character_name", names["web"])
            page.screenshot(path=str(output / "account-create.png"))
            click("create_submit")
            wait("browser_creation_is_server_confirmed", lambda: selection_ready(names["web"]))
            wait(
                "native_creation_is_server_confirmed",
                lambda: (
                    bool(selected(desktop(), names["native"]))
                    and account(desktop()).get("selected_id")
                    == selected(desktop(), names["native"])
                ),
            )
            web_id, native_id = selected(web(), names["web"]), selected(desktop(), names["native"])
            web_account = account()["account_identity"]
            native_account = account(desktop())["account_identity"]
            assert web_account != native_account and web_id != native_id
            assert len(account()["characters"]) == len(account(desktop())["characters"]) == 1
            checks.append("independent_accounts_receive_only_their_own_rosters")
            page.screenshot(path=str(output / "account-select.png"))
            native_command("enter")
            click("enter")
            wait(
                "both_selected_characters_enter_world",
                lambda: (
                    web().get("connection_state")
                    == desktop().get("connection_state")
                    == "connected"
                ),
                90,
            )
            wait(
                "mutual_rendered_character_visibility",
                lambda: seen(web(), native_id) is not None and seen(desktop(), web_id) is not None,
                60,
            )
            samples["initial_web"], samples["initial_native"] = web(), desktop()
            page.screenshot(path=str(output / "account-world.png"))
            native_command("capture")
            wait("native_initial_world_capture_saved", lambda: (output / "desktop.png").is_file())
            (output / "desktop.png").replace(output / "desktop-initial.png")
            start = seen(desktop(), web_id)
            page.locator("canvas").focus()
            page.keyboard.down("w")
            try:
                wait(
                    "browser_WASD_reaches_native_rendered_avatar",
                    lambda: distance(seen(desktop(), web_id), start) > 0.5,
                    8,
                )
            finally:
                page.keyboard.up("w")
            first_position = settle(web_id, "browser_movement_settles")
            start = seen(web(), native_id)
            native_command("move", x=-1, z=0)
            wait(
                "native_movement_reaches_browser_rendered_avatar",
                lambda: distance(seen(web(), native_id), start) > 0.5,
                8,
            )
            native_command("stop")
            error_count = len(web().get("errors", []))
            web_command("move", x=2, z=0)
            wait(
                "server_rejects_invalid_account_movement",
                lambda: len(web().get("errors", [])) > error_count,
            )
            settle(web_id, "rejected_movement_leaves_character_stopped")

            native_command("leave")
            wait(
                "native_leave_removes_browser_presence",
                lambda: (
                    desktop().get("connection_state") == "lobby" and seen(web(), native_id) is None
                ),
            )
            error_count = len(desktop().get("errors", []))
            native_command("select", character_id=web_id)
            wait(
                "foreign_character_selection_is_rejected",
                lambda: len(desktop().get("errors", [])) > error_count,
            )
            assert account(desktop())["selected_id"] == native_id
            checks.append("rejected_selection_preserves_owned_character")
            native_command("enter")
            wait("native_owned_character_returns", lambda: seen(web(), native_id) is not None)
            if args.panels:
                samples["panels"] = exercise_panels(page, web, wait, output)
            if args.inventory:
                samples["inventory"] = exercise_inventory(page, web, wait, output)
            first_position = settle(web_id, "first_character_position_saved_before_switch")
            system_action("change_character")
            stage("select", "change_character_returns_to_selection")
            wait("lobby_has_no_world_presence", lambda: seen(desktop(), web_id) is None)
            click("slot_next")
            wait("original_arrow_selects_empty_second_slot", lambda: account().get("slot") == 1)
            click("create_open")
            stage("create", "empty_slot_opens_creation")
            fill("character_name", names["native"])
            error_count = len(web().get("errors", []))
            click("create_submit")
            wait(
                "duplicate_character_name_is_rejected",
                lambda: len(web().get("errors", [])) > error_count and not account().get("busy"),
            )
            assert account()["stage"] == "create" and account()["roster_count"] == 1
            checks.append("creation_rejection_preserves_form_and_roster")
            fill("character_name", names["second"])
            click("create_submit")
            wait("second_character_creation_is_confirmed", lambda: selection_ready(names["second"]))
            second_id = selected(web(), names["second"])
            assert second_id not in [web_id, native_id]
            page.screenshot(path=str(output / "account-two-characters.png"))
            click("enter")
            wait(
                "second_character_enters_with_distinct_presence",
                lambda: seen(desktop(), second_id) is not None and seen(desktop(), web_id) is None,
            )
            system_action("change_character")
            stage("select", "second_character_leaves_for_selection")
            page.keyboard.press("1")
            wait("original_slot_key_selects_first_character", lambda: selection_ready(names["web"]))
            click("enter")
            wait(
                "first_character_position_survives_switch",
                lambda: (
                    distance(seen(desktop(), web_id), first_position) < 0.1
                    and seen(desktop(), second_id) is None
                ),
            )
            position = settle(web_id, "first_character_stops_before_reconnect")
            web_command("disconnect")
            wait(
                "account_disconnect_removes_remote_avatar", lambda: seen(desktop(), web_id) is None
            )
            web_command("reconnect")
            wait(
                "account_reconnect_restores_selected_character",
                lambda: (
                    web().get("identity") == web_id
                    and distance(seen(desktop(), web_id), position) < 0.1
                ),
                60,
            )
            page.reload(wait_until="domcontentloaded")
            stage("select", "browser_reload_restores_account_to_selection", 90)
            assert account()["account_identity"] == web_account and account()["roster_count"] == 2
            assert account()["selected_id"] == web_id and web()["connection_state"] == "lobby"
            checks.append("session_restore_keeps_account_roster_and_selection")
            click("enter")
            wait(
                "restored_session_enters_original_character",
                lambda: distance(seen(desktop(), web_id), position) < 0.1,
            )
            if args.inventory:
                wait(
                    "account_restore_preserves_character_inventory",
                    lambda: (
                        sorted(web().get("inventory", []), key=lambda row: row["id"])
                        == sorted(
                            [samples["inventory"]["sword"], samples["inventory"]["potion"]],
                            key=lambda row: row["id"],
                        )
                    ),
                )

            native_command("logout")
            wait(
                "native_logout_removes_presence",
                lambda: (
                    seen(web(), native_id) is None
                    and not account(desktop()).get("account_identity")
                ),
            )
            native_command(
                "login",
                username=credentials["native"]["username"],
                password=credentials["native"]["password"],
            )
            wait(
                "native_username_login_restores_owned_roster",
                lambda: (
                    desktop().get("connection_state") == "lobby"
                    and account(desktop()).get("account_identity") == native_account
                    and account(desktop()).get("selected_id") == native_id
                ),
            )
            native_command("enter")
            wait(
                "native_login_restores_rendered_character",
                lambda: seen(web(), native_id) is not None,
            )
            system_action("logout")
            stage("login", "browser_logout_returns_to_login")
            wait("browser_logout_removes_presence", lambda: seen(desktop(), web_id) is None)
            page.reload(wait_until="domcontentloaded")
            stage("server", "logout_refresh_has_no_saved_session", 90)
            assert not account().get("account_identity") and account()["roster_count"] == 0
            checks.append("logout_clears_account_and_roster")
            wait("server_available_after_logout", lambda: account().get("available"))
            click("server_confirm")
            stage("login", "login_available_after_logout")
            fill("username", credentials["web"]["username"])
            fill("password", "incorrect-" + secrets.token_hex(6))
            click("login_submit")
            wait(
                "wrong_password_remains_on_original_login",
                lambda: (
                    account().get("stage") == "login"
                    and "incorrect" in account().get("message", "").lower()
                    and not account().get("busy")
                ),
            )
            assert not account().get("account_identity")
            checks.append("failed_login_does_not_authorize_account")
            fill("password", credentials["web"]["password"])
            click("login_submit")
            stage("select", "username_password_login_restores_selection")
            assert (
                account()["account_identity"] == web_account and account()["selected_id"] == web_id
            )
            click("enter")
            wait(
                "both_accounts_render_after_logout_and_login",
                lambda: seen(web(), native_id) is not None and seen(desktop(), web_id) is not None,
            )
            page.screenshot(path=str(output / "account-world-final.png"))
            native_command("capture")
            wait("native_render_capture_saved", lambda: (output / "desktop.png").is_file())
            samples["final_web"], samples["final_native"] = web(), desktop()
            if args.session_refresh:
                position = settle(web_id, "character_stops_before_automatic_session_refresh")
                native_command("stop")
                wait(
                    "native_stops_before_automatic_session_refresh",
                    lambda: (
                        desktop().get("activity") == 0
                        and distance(seen(web(), native_id), desktop().get("server_position"))
                        < 0.02
                    ),
                )
                native_position = desktop()["server_position"]
                connection_times = (web()["connected_at_msec"], desktop()["connected_at_msec"])
                assert min(connection_times) > 0
                wait(
                    "both_real_session_timers_refresh_and_restore_world",
                    lambda: (
                        web().get("connection_state")
                        == desktop().get("connection_state")
                        == "connected"
                        and web().get("connected_at_msec", 0) > connection_times[0]
                        and desktop().get("connected_at_msec", 0) > connection_times[1]
                        and web().get("identity") == web_id
                        and desktop().get("identity") == native_id
                        and distance(seen(desktop(), web_id), position) < 0.1
                        and distance(seen(web(), native_id), native_position) < 0.1
                    ),
                    330,
                )
                samples["after_session_refresh_web"] = web()
                samples["after_session_refresh_native"] = desktop()
                page.screenshot(path=str(output / "account-session-refresh.png"))
            assert not browser_errors, "Browser engine errors: " + "; ".join(browser_errors[:3])
            checks.append("browser_has_no_engine_errors")
            passed = True
            context.close()
            browser.close()
    except Exception as error:
        failure = redact(str(error))
        if page is not None and not page.is_closed():
            with contextlib.suppress(Exception):
                samples["failed_web"] = web()
                page.screenshot(path=str(output / "failure.png"))
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
        log.close()
        native_log = redact((output / "desktop.log").read_text())
        private_write(output / "desktop.log", native_log)
        if "SCRIPT ERROR:" in native_log or "\nERROR:" in native_log:
            passed = False
            failure = failure or "Native client reported an engine error; see desktop.log"
        result = {
            "passed": passed,
            "failure": failure,
            "url": args.url,
            "database": args.database,
            "checks": checks,
            "samples": samples,
            "desktop_final": desktop(),
            "browser_errors": browser_errors,
        }
        private_write(output / "report.json", redact(json.dumps(result, indent=2)) + "\n")
        for path in [command_path, command_path.with_suffix(".tmp")]:
            path.unlink(missing_ok=True)
        # Only fresh test-owned userdata is removed, including local session material.
        for directory in [output / "data", output / "config"]:
            shutil.rmtree(directory, ignore_errors=True)
        print("Evidence: " + str(output), flush=True)
    if not passed:
        raise SystemExit(failure or "Exported account checks did not complete")


if __name__ == "__main__":
    main()
