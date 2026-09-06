#!/usr/bin/env python3
"""Exercise rendered Web and exported Linux clients against one real server.

Requires exports with --test-probe. No database queries stand in for subscriptions.
"""

import argparse
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def distance(a, b):
    return math.dist([a[0], a[-1]], [b[0], b[-1]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://kcanakdag.com:8443")
    parser.add_argument("--database", default="mt2-browser-proof")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument(
        "--hardware", action="store_true", help="Use a visible Chrome window and the system GPU"
    )
    parser.add_argument(
        "--combat", action="store_true", help="Exercise Yongan combat with keyboard controls"
    )
    parser.add_argument(
        "--restart-host", help="Replace only the game's DB container to test persistence"
    )
    args = parser.parse_args()
    if args.restart_host and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.@-]*", args.restart_host):
        parser.error("Restart host must be a plain SSH host")
    output = ROOT / ".local/browser-proof" / time.strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True)
    report = output / "desktop.json"
    commands = output / "commands.json"
    env = {
        **os.environ,
        "XDG_DATA_HOME": str(output / "data"),
        "XDG_CONFIG_HOME": str(output / "config"),
    }
    checks = []
    samples = {}
    sequence = 0
    page = None
    browser_errors = []

    def desktop():
        try:
            return json.loads(report.read_text())
        except (OSError, ValueError):
            return {}

    def native_command(action, **kwargs):
        nonlocal sequence
        sequence += 1
        temp = commands.with_suffix(".tmp")
        temp.write_text(json.dumps({"sequence": sequence, "action": action, **kwargs}))
        temp.replace(commands)

    def wait(name, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                checks.append(name)
                print("PASS " + name, flush=True)
                return
            time.sleep(0.1)
        if page is not None and not page.is_closed():
            samples["failed_web"] = page.evaluate("() => JSON.parse(window.mt2Snapshot || '{}')")
            page.screenshot(path=str(output / "failure.png"))
        raise AssertionError(name + " timed out")

    log = (output / "desktop.log").open("w")
    process = subprocess.Popen(
        [
            "xvfb-run",
            "-a",
            str(ROOT / "dist/linux-test/MT2Spacetime.x86_64"),
            "--",
            "--server",
            args.url,
            "--database",
            args.database,
            "--name",
            "DesktopTest",
            "--profile",
            "browser-proof",
            "--auto-connect",
            "--probe-report",
            str(report),
            "--probe-commands",
            str(commands),
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    started = time.monotonic()
    try:
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
                    browser_errors.append(
                        re.sub(r"([?&]token=)[^ &]+", r"\1[REDACTED]", message.text)
                    )
                    if message.type == "error"
                    and message.text.lstrip().startswith(("ERROR:", "SCRIPT ERROR:", "Uncaught "))
                    else None
                ),
            )
            page.goto(args.url, wait_until="domcontentloaded")

            def web():
                return page.evaluate("() => JSON.parse(window.mt2Snapshot || '{}')")

            def web_command(action, **kwargs):
                page.evaluate(
                    "c => window.mt2Command(JSON.stringify(c))", {"action": action, **kwargs}
                )

            def seen(snapshot, identity):
                return next(
                    (
                        a["position"]
                        for a in snapshot.get("rendered_actors", [])
                        if a["identity"] == identity
                    ),
                    None,
                )

            wait("browser_engine_started", lambda: bool(web()), 90)
            samples["engine_ready_seconds"] = round(time.monotonic() - started, 2)
            web_command("connect", name="BrowserTest")
            wait(
                "both_exported_clients_connected",
                lambda: (
                    web().get("connection_state") == "connected"
                    and desktop().get("connection_state") == "connected"
                ),
                90,
            )
            samples["world_ready_seconds"] = round(time.monotonic() - started, 2)
            web_id, native_id = web()["identity"], desktop()["identity"]
            assert web_id != native_id
            checks.append("independent_identities")
            wait(
                "mutual_rendered_visibility",
                lambda: seen(web(), native_id) is not None and seen(desktop(), web_id) is not None,
            )
            samples["initial_web"], samples["initial_desktop"] = web(), desktop()
            if web().get("map_chunks"):
                wait("background_scenery_loads", lambda: len(web().get("map_chunks", [])) >= 2)
            start = seen(desktop(), web_id)
            web_command("move", x=1, z=0)
            wait(
                "browser_movement_reaches_desktop_avatar",
                lambda: distance(seen(desktop(), web_id), start) > 0.5,
                4,
            )
            web_command("stop")
            start = seen(web(), native_id)
            native_command("move", x=-1, z=0)
            wait(
                "desktop_movement_reaches_browser_avatar",
                lambda: distance(seen(web(), native_id), start) > 0.5,
                4,
            )
            native_command("stop")
            start = seen(desktop(), web_id)
            page.locator("canvas").focus()
            page.keyboard.down("w")
            try:
                wait(
                    "browser_keyboard_moves_authoritative_avatar",
                    lambda: distance(seen(desktop(), web_id), start) > 0.5,
                    6,
                )
            finally:
                page.keyboard.up("w")
            web_command("stop")
            web_command("move", x=2, z=0)
            wait("browser_reducer_rejection", lambda: bool(web().get("errors")))
            assert web()["connection_state"] == "connected"
            page.screenshot(path=str(output / "browser.png"))
            native_command("capture")
            samples["moved_web"], samples["moved_desktop"] = web(), desktop()
            position = seen(desktop(), web_id)
            web_command("disconnect")
            wait(
                "browser_disconnect_removes_desktop_avatar", lambda: seen(desktop(), web_id) is None
            )
            web_command("reconnect")
            wait(
                "browser_reconnect_restores_avatar",
                lambda: web().get("identity") == web_id and seen(desktop(), web_id) is not None,
            )
            assert distance(seen(desktop(), web_id), position) < 0.1
            checks.append("browser_reconnect_preserves_position")
            page.reload(wait_until="domcontentloaded")
            wait("browser_refresh_boots", lambda: bool(web()), 90)
            web_command("connect", name="BrowserTest")
            wait(
                "browser_refresh_preserves_identity",
                lambda: (
                    web().get("connection_state") == "connected" and web().get("identity") == web_id
                ),
            )
            native_command("disconnect")
            wait(
                "desktop_disconnect_removes_browser_avatar", lambda: seen(web(), native_id) is None
            )
            native_command("reconnect")
            wait(
                "desktop_reconnect_restores_browser_avatar",
                lambda: (
                    seen(web(), native_id) is not None and desktop().get("identity") == native_id
                ),
            )
            samples["final_web"], samples["final_desktop"] = web(), desktop()
            samples["static_downloads"] = (
                page.evaluate(r"""() => performance.getEntriesByType('resource')
                .filter(r => /\.(pck|wasm|js)$|\/world\/manifest.json$/.test(r.name))
                .map(r => ({path: new URL(r.name).pathname, bytes: r.encodedBodySize,
                            transferred: r.transferSize, duration_ms: r.duration}))""")
            )
            if args.restart_host:
                positions = (web()["server_position"], desktop()["server_position"])
                subprocess.run(
                    [
                        "ssh",
                        "-o",
                        "BatchMode=yes",
                        args.restart_host,
                        "cd /opt/metin2-godotime && docker compose up -d --force-recreate db",
                    ],
                    check=True,
                )
                wait(
                    "container_replacement_disconnects_clients",
                    lambda: (
                        web().get("connection_state") != "connected"
                        and desktop().get("connection_state") != "connected"
                    ),
                )
                time.sleep(2)
                web_command("reconnect")
                native_command("reconnect")
                wait(
                    "container_replacement_preserves_both_identities",
                    lambda: (
                        web().get("connection_state") == "connected"
                        and desktop().get("connection_state") == "connected"
                        and web().get("identity") == web_id
                        and desktop().get("identity") == native_id
                        and seen(web(), native_id) is not None
                        and seen(desktop(), web_id) is not None
                    ),
                    60,
                )
                assert distance(web()["server_position"], positions[0]) < 0.1
                assert distance(desktop()["server_position"], positions[1]) < 0.1
                checks.append("container_replacement_preserves_positions")
                samples["after_replacement_web"] = web()
                samples["after_replacement_desktop"] = desktop()
            if args.combat:

                def local_player(snapshot):
                    return next(row for row in snapshot["player_rows"] if row["identity"] == web_id)

                monster = web()["monsters"][0]
                web_command("target", x=monster["x"], z=monster["z"])
                wait(
                    "browser_approaches_monster",
                    lambda: (
                        distance(
                            web()["server_position"],
                            [web()["monsters"][0]["x"], web()["monsters"][0]["z"]],
                        )
                        < 2.5
                    ),
                    15,
                )
                web_command("stop")
                page.locator("canvas").focus()
                for _ in range(4):
                    page.keyboard.press("Space")
                    time.sleep(1.05)
                wait(
                    "browser_keyboard_attack_kills_monster_for_both_clients",
                    lambda: (
                        web()["monsters"][0]["health"] == 0
                        and desktop()["monsters"][0]["health"] == 0
                        and len(web()["loot"]) == 1
                        and len(desktop()["loot"]) == 1
                    ),
                    8,
                )
                samples["monster_death_web"] = web()
                page.screenshot(path=str(output / "browser-combat.png"))
                page.keyboard.press("e")
                wait(
                    "browser_keyboard_loot_awards_gold_and_removes_both_drops",
                    lambda: (
                        local_player(web())["gold"] == 5
                        and not web()["loot"]
                        and not desktop()["loot"]
                    ),
                )
                wait(
                    "monster_respawns_on_both_clients",
                    lambda: (
                        web()["monsters"][0]["health"] == 100
                        and desktop()["monsters"][0]["health"] == 100
                    ),
                )
                monster = web()["monsters"][0]
                web_command("target", x=monster["x"], z=monster["z"])
                wait(
                    "browser_player_death_replicates",
                    lambda: (
                        local_player(web())["health"] == 0
                        and local_player(desktop())["health"] == 0
                    ),
                )
                samples["player_death_web"] = web()
                wait(
                    "browser_player_respawns_with_gold",
                    lambda: (
                        local_player(web())["health"] == 100
                        and local_player(web())["gold"] == 5
                        and distance(web()["server_position"], [660, 575]) < 0.1
                    ),
                )
                samples["combat_final_web"] = web()
            page.screenshot(path=str(output / "browser-final.png"))
            assert not browser_errors, "Browser console errors: " + "; ".join(browser_errors[:3])
            checks.append("browser_has_no_engine_errors")
            context.close()
            browser.close()
    finally:
        # Terminate only the process group created by this test, including its Xvfb child.
        import signal

        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
        log.close()
        result = {
            "url": args.url,
            "database": args.database,
            "checks": checks,
            "samples": samples,
            "desktop_final": desktop(),
            "browser_errors": browser_errors,
        }
        (output / "report.json").write_text(json.dumps(result, indent=2) + "\n")
        print("Evidence: " + str(output), flush=True)


if __name__ == "__main__":
    main()
