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

from browser_snapshot import (
    POSITION_INVALID,
    POSITION_VALID,
    SnapshotUnavailableError,
    authoritative_position_distance,
    read_fresh_json_snapshot,
    subscribed_player_position,
)
from playwright.sync_api import sync_playwright
from test_browser import distance
from test_browser_actors import exercise_actors
from test_browser_classes import exercise_class_world, exercise_previews
from test_browser_combo import exercise_combo
from test_browser_finisher import (
    exercise_finisher,
    heal_finisher_browser,
    park_finisher_clients,
)
from test_browser_inventory import exercise_inventory
from test_browser_mobs import exercise_field, population_summary
from test_browser_npcs import exercise_npcs, npc
from test_browser_panels import exercise_panels
from test_browser_physical import exercise_physical
from test_browser_progression import exercise_progression, exercise_progression_combat
from test_browser_target import exercise_targeting
from test_browser_training import exercise_training_dummy
from test_probe_activation import exercise_ordinary_world

ROOT = Path(__file__).resolve().parents[1]
RENEWAL_INPUT_AUDIT = """() => {
    const movementCodes = new Set([
        "KeyW", "KeyA", "KeyS", "KeyD",
        "ArrowUp", "ArrowLeft", "ArrowDown", "ArrowRight"
    ]);
    const audit = {
        installedAtMs: performance.now(),
        events: [],
        pressed: [],
        pointerButtons: 0
    };
    const append = value => {
        audit.events.push({...value, atMs: performance.now()});
        if (audit.events.length > 128) audit.events.shift();
    };
    window.addEventListener("keydown", event => {
        if (!movementCodes.has(event.code)) return;
        if (!audit.pressed.includes(event.code)) audit.pressed.push(event.code);
        append({type: "keydown", code: event.code, repeat: event.repeat,
            target: event.target?.tagName || ""});
    }, true);
    window.addEventListener("keyup", event => {
        if (!movementCodes.has(event.code)) return;
        audit.pressed = audit.pressed.filter(code => code !== event.code);
        append({type: "keyup", code: event.code,
            target: event.target?.tagName || ""});
    }, true);
    for (const type of ["pointerdown", "pointerup", "pointercancel"]) {
        window.addEventListener(type, event => {
            if (!(event.target instanceof HTMLCanvasElement)) return;
            audit.pointerButtons = event.buttons;
            append({type, button: event.button, buttons: event.buttons,
                x: event.clientX, y: event.clientY, target: "CANVAS"});
        }, true);
    }
    window.addEventListener("blur", () => append({type: "window-blur"}), true);
    window.addEventListener("focus", () => append({type: "window-focus"}), true);
    document.addEventListener("visibilitychange", () => append({
        type: "visibility", state: document.visibilityState
    }), true);
    window.mt2RenewalInputAudit = audit;
}"""
WEBGL_RENDERER_PROBE = """() => {
    const canvas = document.createElement("canvas");
    const attributes = {alpha: false, antialias: false, preserveDrawingBuffer: false};
    const gl = canvas.getContext("webgl2", attributes) || canvas.getContext("webgl", attributes);
    if (!gl) return {available: false};
    const debug = gl.getExtension("WEBGL_debug_renderer_info");
    const result = {
        available: true,
        api: gl instanceof WebGL2RenderingContext ? "webgl2" : "webgl",
        vendor: String(gl.getParameter(debug ? debug.UNMASKED_VENDOR_WEBGL : gl.VENDOR)),
        renderer: String(gl.getParameter(debug ? debug.UNMASKED_RENDERER_WEBGL : gl.RENDERER)),
        version: String(gl.getParameter(gl.VERSION)),
        shading_language: String(gl.getParameter(gl.SHADING_LANGUAGE_VERSION))
    };
    const lose = gl.getExtension("WEBGL_lose_context");
    if (lose) lose.loseContext();
    return result;
}"""


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


def progression(snapshot: dict, identity: str) -> dict:
    return next(
        (row for row in snapshot.get("progression", []) if row.get("character_id") == identity),
        {},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://kcanakdag.com:8443")
    parser.add_argument("--database", default="mt2-browser-proof")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument(
        "--hardware",
        action="store_true",
        help="Use the system GPU and show Chrome unless --headless is also set",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Hide Chrome; combine with --hardware to retain the system GPU",
    )
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--actors", action="store_true")
    parser.add_argument(
        "--ground-items",
        action="store_true",
        help="Verify original ground models after field combat",
    )
    parser.add_argument("--field-combat", action="store_true", help="Attack an original field mob")
    parser.add_argument(
        "--profile-probe",
        action="store_true",
        help="Measure field FPS with probe snapshots suspended",
    )
    parser.add_argument(
        "--field-only", action="store_true", help="Stop after field rendering/performance checks"
    )
    parser.add_argument(
        "--mob-route", type=Path, help="Walk both exports to original field mobs and back"
    )
    parser.add_argument(
        "--mob-catalog", type=Path, help="Validate the full original mob population"
    )
    parser.add_argument("--panels", action="store_true")
    parser.add_argument(
        "--classes",
        action="store_true",
        help="Check all eight previews and play Ninja/Shaman through original creation controls",
    )
    parser.add_argument(
        "--world-npcs", type=Path, help="Check original NPCs using a map-bound walking route JSON"
    )
    parser.add_argument("--progression", action="store_true")
    parser.add_argument(
        "--physical",
        action="store_true",
        help="Check protocol-10 Attack/Defense, Sword tooltips and equipment in the Training fixture",
    )
    parser.add_argument(
        "--targeting",
        action="store_true",
        help="Exercise protocol-9 target picking, private UI, effects, combat, and cleanup",
    )
    parser.add_argument(
        "--combo",
        action="store_true",
        help="Exercise both exported clients' protocol-9 three-step Sword+0 prefix and root travel",
    )
    parser.add_argument(
        "--finisher",
        action="store_true",
        help="Exercise the protocol-9 four-step combo in its exact three-dog Training fixture",
    )
    parser.add_argument(
        "--progression-combat",
        action="store_true",
        help="Kill five production Wild Dogs and allocate the first VIT point",
    )
    parser.add_argument(
        "--session-refresh",
        action="store_true",
        help="Wait for both real four-minute session refresh timers while in world",
    )
    parser.add_argument("--native", type=Path, default=ROOT / "dist/linux-test/MT2Spacetime.x86_64")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--ordinary-reload",
        action="store_true",
        help="After --field-only, verify an ordinary browser without the QA probe using its peer",
    )
    parser.add_argument(
        "--skills",
        action="store_true",
        help="Exercise K/Escape skill-panel input in exported clients",
    )
    parser.add_argument(
        "--warrior-effects",
        action="store_true",
        help="With --classes, exercise female Warrior finisher waves as the second character",
    )
    parser.add_argument(
        "--training-dummy",
        action="store_true",
        help="Exercise the authored dummy with real browser pointer and Space input",
    )
    args = parser.parse_args()
    if args.ordinary_reload and not args.field_only:
        parser.error("--ordinary-reload requires --field-only")
    if args.ground_items and not args.field_combat:
        parser.error("--ground-items requires --field-combat")
    if args.field_combat and not args.mob_route:
        parser.error("--field-combat requires --mob-route")
    if args.profile_probe and not args.mob_route:
        parser.error("--profile-probe requires --mob-route")
    if args.field_only and not args.mob_route:
        parser.error("--field-only requires --mob-route")
    if args.warrior_effects and not args.classes:
        parser.error("--warrior-effects requires --classes")
    if args.classes and any(
        (
            args.inventory,
            args.actors,
            args.physical,
            args.finisher,
            args.targeting,
            args.combo,
            args.progression,
            args.progression_combat,
        )
    ):
        parser.error(
            "--classes exercises its own creation/equipment scenario; omit Warrior fixture flags"
        )
    npc_route = json.loads(args.world_npcs.read_text()) if args.world_npcs else None
    if args.world_npcs and any(
        (args.physical, args.finisher, args.targeting, args.combo, args.progression_combat)
    ):
        parser.error("--world-npcs uses the normal Yongan population; omit combat fixture flags")
    if args.physical and any(
        (
            args.inventory,
            args.actors,
            args.panels,
            args.progression,
            args.targeting,
            args.combo,
            args.finisher,
            args.progression_combat,
        )
    ):
        parser.error("--physical uses a focused Training UI scenario; omit other feature flags")
    if args.progression_combat and not args.progression:
        parser.error("--progression-combat requires --progression")
    if args.targeting and args.progression_combat:
        parser.error("--targeting cannot be combined with the five-kill --progression-combat mode")
    if args.combo and not (args.targeting and args.inventory and args.actors):
        parser.error("--combo requires --targeting --inventory --actors")
    if args.finisher and not (args.inventory and args.actors):
        parser.error("--finisher requires --inventory --actors")
    if args.finisher and args.panels:
        parser.error(
            "--panels needs original-map metadata and cannot run in the --finisher fixture"
        )
    if args.finisher and (args.targeting or args.combo or args.progression_combat):
        parser.error(
            "--finisher uses its separate Training fixture and cannot be combined with "
            "Yongan targeting, combo, or progression combat"
        )
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
    last_web_snapshot: dict = {}
    native_snapshot_ready = False
    native_snapshot_reads = {
        "recovered_count": 0,
        "unavailable_count": 0,
        "max_attempts": 1,
        "max_elapsed_seconds": 0.0,
        "events": [],
    }
    samples["native_snapshot_reads"] = native_snapshot_reads
    started = time.monotonic()

    def redact(text: str) -> str:
        for value in protected:
            text = text.replace(value, "[REDACTED]")
        return re.sub(r"([?&]token=)[^ &]+", r"\1[REDACTED]", text)

    def desktop() -> dict:
        nonlocal native_snapshot_ready
        try:
            snapshot, attempts, elapsed = read_fresh_json_snapshot(report_path)
        except SnapshotUnavailableError as error:
            native_snapshot_reads["unavailable_count"] += 1
            native_snapshot_reads["max_attempts"] = max(
                native_snapshot_reads["max_attempts"], error.attempts
            )
            native_snapshot_reads["max_elapsed_seconds"] = max(
                native_snapshot_reads["max_elapsed_seconds"], round(error.elapsed, 3)
            )
            native_snapshot_reads["events"].append(
                {
                    "result": "unavailable",
                    "startup": not native_snapshot_ready,
                    "attempts": error.attempts,
                    "elapsed_seconds": round(error.elapsed, 3),
                    "reason": error.reason,
                }
            )
            del native_snapshot_reads["events"][:-32]
            raise
        native_snapshot_ready = True
        native_snapshot_reads["max_attempts"] = max(native_snapshot_reads["max_attempts"], attempts)
        native_snapshot_reads["max_elapsed_seconds"] = max(
            native_snapshot_reads["max_elapsed_seconds"], round(elapsed, 3)
        )
        if attempts > 1:
            native_snapshot_reads["recovered_count"] += 1
            native_snapshot_reads["events"].append(
                {
                    "result": "recovered",
                    "attempts": attempts,
                    "elapsed_seconds": round(elapsed, 3),
                }
            )
            del native_snapshot_reads["events"][:-32]
        return snapshot

    def native_boot_ready() -> bool:
        try:
            return bool(account(desktop()))
        except SnapshotUnavailableError:
            return False

    def native_command(action: str, **values) -> None:
        nonlocal sequence
        sequence += 1
        temporary = command_path.with_suffix(".tmp")
        private_write(temporary, json.dumps({"sequence": sequence, "action": action, **values}))
        temporary.replace(command_path)

    def web() -> dict:
        nonlocal last_web_snapshot
        snapshot = page.evaluate("() => JSON.parse(window.mt2Snapshot || '{}')")
        if isinstance(snapshot, dict):
            last_web_snapshot = snapshot
        return snapshot

    def account(snapshot=None) -> dict:
        return (web() if snapshot is None else snapshot).get("account", {})

    def web_command(action: str, **values) -> None:
        page.evaluate("c => window.mt2Command(JSON.stringify(c))", {"action": action, **values})

    def wait(name, predicate, timeout=30, poll_interval=0.1) -> None:
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
            time.sleep(poll_interval)
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

        def settled() -> bool:
            web_state, native_state = web(), desktop()
            status, position = subscribed_player_position(web_state, identity)
            if status == POSITION_INVALID:
                raise AssertionError(
                    "subscribed own player row has invalid authoritative coordinates"
                )
            return (
                status == POSITION_VALID
                and web_state.get("activity") == 0
                and any(
                    row["identity"] == identity and row["activity"] == 0
                    for row in native_state.get("player_rows", [])
                )
                and distance(seen(native_state, identity), position) < 0.02
            )

        wait(
            check,
            settled,
        )
        status, position = subscribed_player_position(web(), identity)
        assert status == POSITION_VALID and position is not None
        return position

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
            browser_headless = args.headless or not args.hardware
            if args.hardware:
                chrome_arguments = ["--enable-gpu"] if browser_headless else []
            else:
                chrome_arguments = [
                    "--use-angle=swiftshader",
                    "--enable-unsafe-swiftshader",
                    "--disable-dev-shm-usage",
                ]
            browser = playwright.chromium.launch(
                executable_path=args.chrome,
                headless=browser_headless,
                args=chrome_arguments,
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
            page.goto(args.url, wait_until="domcontentloaded")
            wait(
                "both_exported_account_screens_boot",
                lambda: bool(account()) and native_boot_ready(),
                90,
            )
            samples["browser_renderer"] = {
                "requested_hardware": args.hardware,
                "headless": browser_headless,
                "webgl": page.evaluate(WEBGL_RENDERER_PROBE),
            }
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
            if args.classes:
                samples["class_previews"] = exercise_previews(page, account, click, wait, output)
            fill("character_name", names["web"])
            if args.progression:
                page.keyboard.press("c")
                wait(
                    "account_field_C_stays_in_character_name",
                    lambda: (
                        account().get("character_name_input") == names["web"] + "c"
                        and not web()["ui"]["status"]["visible"]
                    ),
                )
                page.keyboard.press("Backspace")
                wait(
                    "character_name_restored_after_C_focus_check",
                    lambda: account().get("character_name_input") == names["web"],
                )
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
            if args.finisher or args.physical:
                samples["finisher_entry_park"] = park_finisher_clients(
                    web,
                    desktop,
                    web_command,
                    native_command,
                    wait,
                    web_id,
                    native_id,
                )
                if args.finisher:
                    samples["finisher_entry_healing"] = heal_finisher_browser(
                        page, web, wait, web_id
                    )
            samples["initial_web"], samples["initial_native"] = web(), desktop()
            if args.mob_catalog:
                catalog = json.loads(args.mob_catalog.read_text())
                samples["original_population"] = population_summary(web(), desktop(), catalog)
                wait("both_exports_receive_full_original_population", lambda: True)
            if args.mob_route:
                samples["field_mobs"] = {}
                exercise_field(
                    page,
                    web,
                    desktop,
                    web_command,
                    native_command,
                    wait,
                    json.loads(args.mob_route.read_text()),
                    output,
                    return_to_town=not args.field_only,
                    profile_probe=args.profile_probe,
                    field_combat=args.field_combat,
                    ground_items=args.ground_items,
                    evidence=samples["field_mobs"],
                )
                if args.field_only:
                    if args.ordinary_reload:
                        samples["ordinary_world"] = exercise_ordinary_world(
                            browser, context, page, desktop, wait, web_id, output
                        )
                    assert not browser_errors, "Browser engine errors: " + "; ".join(
                        browser_errors[:3]
                    )
                    checks.append("browser_has_no_engine_errors")
                    passed = True
                    context.close()
                    browser.close()
                    return
            if args.training_dummy:
                samples["training_dummy"] = exercise_training_dummy(
                    page, web, desktop, web_command, wait, web_id, output
                )
            if args.skills:
                page.keyboard.press("k")
                wait(
                    "skills_key_opens_panel",
                    lambda: web().get("ui", {}).get("skills", {}).get("visible") is True,
                )
                page.screenshot(path=str(output / "skills-first-character.png"))
                page.keyboard.press("Escape")
                wait(
                    "escape_closes_skills",
                    lambda: web().get("ui", {}).get("skills", {}).get("visible") is False,
                )
            if args.classes:
                samples["ninja"] = exercise_class_world(
                    page,
                    web,
                    desktop,
                    wait,
                    web_id,
                    "actor.player.ninja-female",
                    output,
                    weapon_vnum=10,
                    mode="onehand",
                )
            page.screenshot(path=str(output / "account-world.png"))
            native_command("capture")
            wait("native_initial_world_capture_saved", lambda: (output / "desktop.png").is_file())
            (output / "desktop.png").replace(output / "desktop-initial.png")
            if args.physical:
                samples["physical"] = exercise_physical(
                    page, web, desktop, native_command, wait, web_id, native_id, output
                )
            if npc_route:
                samples["world_npcs"] = exercise_npcs(
                    page, web, desktop, web_command, native_command, wait, npc_route, output
                )
            if args.progression:
                samples["progression"] = exercise_progression(
                    page,
                    web,
                    desktop,
                    web_command,
                    wait,
                    web_id,
                    native_id,
                    output,
                )
            if (args.targeting or args.finisher) and args.inventory:
                # Finisher clients have already escaped the aggro-adjacent
                # Training spawn, so the full-health potion rejection remains a
                # real prerequisite rather than racing ordinary monster damage.
                samples["inventory"] = exercise_inventory(page, web, wait, output)
            if args.targeting:
                samples["targeting_diagnostics"] = {}
                samples["targeting"] = exercise_targeting(
                    page,
                    web,
                    desktop,
                    web_command,
                    native_command,
                    wait,
                    web_id,
                    native_id,
                    output,
                    samples["targeting_diagnostics"],
                )
            if args.combo:
                samples["combo_diagnostics"] = {}
                samples["combo"] = exercise_combo(
                    page,
                    web,
                    desktop,
                    web_command,
                    native_command,
                    wait,
                    web_id,
                    native_id,
                    output,
                    samples["combo_diagnostics"],
                )
            if args.finisher:
                samples["finisher_diagnostics"] = {}
                samples["finisher"] = exercise_finisher(
                    page,
                    web,
                    desktop,
                    web_command,
                    native_command,
                    wait,
                    web_id,
                    native_id,
                    output,
                    samples["finisher_diagnostics"],
                )
            if args.actors:
                # Each combat helper restores an unarmed, out-of-range actor.
                # Combo deliberately leaves its final target-clear fixture at
                # 65 HP, but this presentation-only actor attack cannot alter it.
                samples["actors"] = exercise_actors(
                    page,
                    web,
                    desktop,
                    web_command,
                    wait,
                    web_id,
                    native_id,
                    output,
                )
            if args.progression_combat and args.inventory:
                # The inventory quickslot rejection needs the full-health starter
                # state. Combat later leaves deliberately partial HP for the VIT
                # no-heal proof, while its quarter award still stacks onto this item.
                samples["inventory"] = exercise_inventory(page, web, wait, output)
            if args.progression_combat:
                samples["progression_combat_diagnostics"] = {}
                samples["progression_combat"] = exercise_progression_combat(
                    page,
                    web,
                    desktop,
                    web_command,
                    native_command,
                    wait,
                    web_id,
                    native_id,
                    output,
                    samples["progression_combat_diagnostics"],
                )
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
            if npc_route:
                assert not desktop().get("rendered_npcs"), "NPCs remain after leaving the world"
                checks.append("native_leave_clears_NPC_layer")
            wait(
                "foreign_character_selection_is_rejected",
                lambda: len(desktop().get("errors", [])) > error_count,
            )
            assert account(desktop())["selected_id"] == native_id
            checks.append("rejected_selection_preserves_owned_character")
            native_command("enter")
            wait("native_owned_character_returns", lambda: seen(web(), native_id) is not None)
            if npc_route:
                wait(
                    "native_reentry_restores_one_NPC",
                    lambda: bool(npc(desktop(), npc_route["spawn_id"])),
                )
            if args.panels:
                samples["panels"] = exercise_panels(page, web, wait, output)
            if args.inventory and "inventory" not in samples:
                samples["inventory"] = exercise_inventory(page, web, wait, output)
            first_position = settle(web_id, "first_character_position_saved_before_switch")
            system_action("change_character")
            stage("select", "change_character_returns_to_selection")
            wait("lobby_has_no_world_presence", lambda: seen(desktop(), web_id) is None)
            click("slot_next")
            wait("original_arrow_selects_empty_second_slot", lambda: account().get("slot") == 1)
            click("create_open")
            stage("create", "empty_slot_opens_creation")
            if args.classes:
                for _ in range(3 if args.warrior_effects else 2):
                    click("slot_next")
                click("female" if args.warrior_effects else "male")
                wait(
                    "second_creation_selects_requested_class",
                    lambda: (
                        account().get("character_class") == (0 if args.warrior_effects else 3)
                        and account().get("sex") == (1 if args.warrior_effects else 0)
                    ),
                )
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
            if args.classes:
                samples["second_class"] = exercise_class_world(
                    page,
                    web,
                    desktop,
                    wait,
                    second_id,
                    "actor.player.warrior-female"
                    if args.warrior_effects
                    else "actor.player.shaman-male",
                    output,
                    weapon_vnum=10 if args.warrior_effects else 7000,
                    mode="onehand" if args.warrior_effects else "fan",
                    camera_wave=args.warrior_effects,
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
            if npc_route:
                wait(
                    "browser_reconnect_restores_one_NPC",
                    lambda: bool(npc(web(), npc_route["spawn_id"])),
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
            if args.progression_combat:
                expected_progression = samples["progression_combat"]["after_vitality"]
                peer_progression = samples["progression_combat"]["peer_progression"]
                wait(
                    "positive_progression_survives_switch_reconnect_and_reload",
                    lambda: (
                        progression(web(), web_id) == expected_progression
                        and progression(desktop(), native_id) == peer_progression
                        and not progression(web(), native_id)
                        and not progression(desktop(), web_id)
                    ),
                )
            if args.inventory:
                expected_inventory = (
                    samples["progression_combat"]["inventory"]
                    if args.progression_combat
                    else [samples["inventory"]["sword"], samples["inventory"]["potion"]]
                )
                wait(
                    "account_restore_preserves_character_inventory",
                    lambda: (
                        sorted(web().get("inventory", []), key=lambda row: row["id"])
                        == sorted(expected_inventory, key=lambda row: row["id"])
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
            if args.progression_combat:
                wait(
                    "positive_progression_survives_both_account_logins",
                    lambda: (
                        progression(web(), web_id) == expected_progression
                        and progression(desktop(), native_id) == peer_progression
                        and not progression(web(), native_id)
                        and not progression(desktop(), web_id)
                    ),
                )
            page.screenshot(path=str(output / "account-world-final.png"))
            native_command("capture")
            wait("native_render_capture_saved", lambda: (output / "desktop.png").is_file())
            samples["final_web"], samples["final_native"] = web(), desktop()
            if args.session_refresh:
                position = settle(web_id, "character_stops_before_automatic_session_refresh")
                native_command("stop")

                def native_stopped() -> bool:
                    native_state, web_state = desktop(), web()
                    status, authoritative = subscribed_player_position(native_state, native_id)
                    if status == POSITION_INVALID:
                        raise AssertionError(
                            "subscribed own player row has invalid authoritative coordinates"
                        )
                    return (
                        status == POSITION_VALID
                        and any(
                            row.get("identity") == native_id and row.get("activity") == 0
                            for row in native_state.get("player_rows", [])
                        )
                        and distance(seen(web_state, native_id), authoritative) < 0.02
                    )

                wait(
                    "native_stops_before_automatic_session_refresh",
                    native_stopped,
                )
                baseline_web, baseline_native = web(), desktop()
                web_status, web_baseline = subscribed_player_position(baseline_web, web_id)
                native_status, native_position = subscribed_player_position(
                    baseline_native, native_id
                )
                assert web_status == native_status == POSITION_VALID
                assert web_baseline is not None and native_position is not None
                assert distance(web_baseline, position) < 0.02
                position = web_baseline
                connection_times = (
                    baseline_web["connected_at_msec"],
                    baseline_native["connected_at_msec"],
                )
                assert min(connection_times) > 0
                page.evaluate(RENEWAL_INPUT_AUDIT)
                samples["session_refresh_baseline_web"] = baseline_web
                samples["session_refresh_baseline_native"] = baseline_native
                samples["session_refresh_authoritative_baselines"] = {
                    "web": position,
                    "native": native_position,
                }
                renewal_started = time.monotonic()
                renewal_trace: list[dict] = []
                trace_fingerprint = None
                trace_at = 0.0

                def renewal_state() -> bool:
                    nonlocal trace_at, trace_fingerprint
                    web_state, native_state = web(), desktop()
                    audit = page.evaluate("() => window.mt2RenewalInputAudit")
                    now = time.monotonic()
                    web_position_status, web_position = subscribed_player_position(
                        web_state, web_id
                    )
                    native_position_status, current_native_position = subscribed_player_position(
                        native_state, native_id
                    )
                    fingerprint = (
                        web_state.get("connection_state"),
                        native_state.get("connection_state"),
                        web_state.get("connected_at_msec"),
                        native_state.get("connected_at_msec"),
                        web_state.get("activity"),
                        native_state.get("activity"),
                        web_position_status,
                        native_position_status,
                        tuple(web_position or []),
                        tuple(current_native_position or []),
                        len(audit.get("events", [])),
                    )
                    if fingerprint != trace_fingerprint or now - trace_at >= 5:
                        events = audit.get("events", [])
                        renewal_trace.append(
                            {
                                "elapsed_seconds": round(now - renewal_started, 3),
                                "web": {
                                    "connection_state": web_state.get("connection_state"),
                                    "connected_at_msec": web_state.get("connected_at_msec"),
                                    "identity": web_state.get("identity"),
                                    "activity": web_state.get("activity"),
                                    "authoritative_position_status": web_position_status,
                                    "authoritative_position": web_position,
                                    "snapshot_server_position": web_state.get("server_position"),
                                    "self_position": seen(web_state, web_id),
                                    "peer_position": seen(native_state, web_id),
                                },
                                "native": {
                                    "connection_state": native_state.get("connection_state"),
                                    "connected_at_msec": native_state.get("connected_at_msec"),
                                    "identity": native_state.get("identity"),
                                    "activity": native_state.get("activity"),
                                    "authoritative_position_status": native_position_status,
                                    "authoritative_position": current_native_position,
                                    "snapshot_server_position": native_state.get("server_position"),
                                    "self_position": seen(native_state, native_id),
                                    "peer_position": seen(web_state, native_id),
                                },
                                "input": {
                                    "pressed": audit.get("pressed", []),
                                    "pointer_buttons": audit.get("pointerButtons", 0),
                                    "event_count": len(events),
                                    "last_event": events[-1] if events else None,
                                },
                            }
                        )
                        samples["session_refresh_trace"] = renewal_trace
                        trace_fingerprint = fingerprint
                        trace_at = now
                    if POSITION_INVALID in (web_position_status, native_position_status):
                        samples["session_refresh_invalid_authoritative_position"] = {
                            "elapsed_seconds": round(now - renewal_started, 3),
                            "web_position_status": web_position_status,
                            "native_position_status": native_position_status,
                            "web": web_state,
                            "native": native_state,
                            "input": audit,
                        }
                        raise AssertionError(
                            "subscribed own player row has invalid authoritative coordinates"
                        )
                    web_drift = (
                        authoritative_position_distance(web_position, position)
                        if web_position_status == POSITION_VALID
                        else None
                    )
                    native_drift = (
                        authoritative_position_distance(current_native_position, native_position)
                        if native_position_status == POSITION_VALID
                        else None
                    )
                    if (
                        web_state.get("connection_state") == "connected"
                        and web_state.get("identity") == web_id
                        and web_position_status == POSITION_VALID
                        and web_drift >= 0.1
                    ) or (
                        native_state.get("connection_state") == "connected"
                        and native_state.get("identity") == native_id
                        and native_position_status == POSITION_VALID
                        and native_drift >= 0.1
                    ):
                        samples["session_refresh_first_valid_drift"] = {
                            "elapsed_seconds": round(now - renewal_started, 3),
                            "web_distance": web_drift,
                            "native_distance": native_drift,
                            "web_authoritative_position": web_position,
                            "native_authoritative_position": current_native_position,
                            "web": web_state,
                            "native": native_state,
                            "input": audit,
                        }
                        raise AssertionError(
                            "authoritative position drifted during session renewal; "
                            "see session_refresh_first_valid_drift"
                        )
                    return (
                        web_state.get("connection_state")
                        == native_state.get("connection_state")
                        == "connected"
                        and web_state.get("connected_at_msec", 0) > connection_times[0]
                        and native_state.get("connected_at_msec", 0) > connection_times[1]
                        and web_state.get("identity") == web_id
                        and native_state.get("identity") == native_id
                        and web_position_status == POSITION_VALID
                        and native_position_status == POSITION_VALID
                        and web_drift < 0.1
                        and native_drift < 0.1
                        and distance(seen(web_state, web_id), position) < 0.1
                        and distance(seen(native_state, web_id), position) < 0.1
                        and distance(seen(native_state, native_id), native_position) < 0.1
                        and distance(seen(web_state, native_id), native_position) < 0.1
                    )

                wait(
                    "both_real_session_timers_refresh_and_restore_world",
                    renewal_state,
                    330,
                )
                samples["session_refresh_input"] = page.evaluate(
                    "() => window.mt2RenewalInputAudit"
                )
                samples["after_session_refresh_web"] = web()
                samples["after_session_refresh_native"] = desktop()
                if args.progression_combat:
                    wait(
                        "positive_progression_survives_both_real_session_refreshes",
                        lambda: (
                            progression(web(), web_id) == expected_progression
                            and progression(desktop(), native_id) == peer_progression
                            and not progression(web(), native_id)
                            and not progression(desktop(), web_id)
                        ),
                    )
                page.screenshot(path=str(output / "account-session-refresh.png"))
            assert not browser_errors, "Browser engine errors: " + "; ".join(browser_errors[:3])
            checks.append("browser_has_no_engine_errors")
            passed = True
            context.close()
            browser.close()
    except Exception as error:
        failure = redact(str(error))
        if last_web_snapshot:
            samples["last_successful_web"] = last_web_snapshot
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
        try:
            desktop_final = desktop()
        except SnapshotUnavailableError as error:
            desktop_final = {"snapshot_unavailable": str(error)}
        result = {
            "passed": passed,
            "scope": "field-only" if args.field_only else "accounts",
            "failure": failure,
            "url": args.url,
            "database": args.database,
            "checks": checks,
            "samples": samples,
            "desktop_final": desktop_final,
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
