#!/usr/bin/env python3
"""Check ordinary and opted-in browser launches against an actual test export."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def collect_console(message, errors, warnings):
    if message.type != "error":
        return
    # Godot warnings/backtrace locations also use console.error. Retain those
    # separately; unknown console errors still fail rather than being suppressed.
    if message.text.lstrip().startswith(("WARNING:", "at: ")):
        warnings.append(message.text)
    else:
        errors.append(message.text)


def browser_cadence(page):
    """Browser animation-frame cadence; intentionally not labeled Godot engine FPS."""
    return page.evaluate("""() => new Promise(resolve => {
        const start = performance.now(); let frames = 0;
        function frame(now) {
            frames++;
            if (now - start >= 5000) resolve({frames, duration_ms: now - start,
                browser_animation_frames_per_second: frames * 1000 / (now - start)});
            else requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
    })""")


def exercise_ordinary_world(browser, context, page, desktop, wait, identity, output):
    """Restore the same account without probe scripts; observe it from its real peer."""
    url = page.url
    instrumented_cadence = browser_cadence(page)
    # Auth storage remains in memory, never in the report or a new credential file.
    storage = context.storage_state(indexed_db=True)
    context.close()

    def present():
        return any(row["identity"] == identity for row in desktop().get("rendered_actors", []))

    wait("ordinary_reload_removes_old_presence", lambda: not present(), 30)
    ordinary = browser.new_context(viewport={"width": 1280, "height": 800}, storage_state=storage)
    try:
        clean_page = ordinary.new_page()
        errors = []
        warnings = []
        clean_page.on("pageerror", lambda error: errors.append(str(error)))
        clean_page.on(
            "console",
            lambda message: collect_console(message, errors, warnings),
        )
        clean_page.goto(url, wait_until="domcontentloaded")
        clean_page.wait_for_selector("#status", state="detached", timeout=90000)
        clean_page.wait_for_timeout(5000)
        clean_page.keyboard.press("Enter")
        wait("ordinary_client_enters_world_seen_by_peer", present, 45)
        assert clean_page.evaluate(
            "typeof window.mt2Command === 'undefined' && typeof window.mt2Snapshot === 'undefined'"
        ), "Ordinary world unexpectedly enabled the probe"
        before = next(
            row["position"] for row in desktop()["rendered_actors"] if row["identity"] == identity
        )
        clean_page.keyboard.down("w")
        try:
            wait(
                "ordinary_WASD_reaches_peer",
                lambda: any(
                    row["identity"] == identity
                    and sum((a - b) ** 2 for a, b in zip(row["position"], before, strict=True))
                    > 0.25
                    for row in desktop().get("rendered_actors", [])
                ),
                10,
            )
        finally:
            clean_page.keyboard.up("w")
        clean_page.wait_for_timeout(1500)
        cadence = browser_cadence(clean_page)
        clean_page.screenshot(path=str(output / "ordinary-world-browser.png"))
        assert not errors, "Ordinary browser errors: " + "; ".join(errors[:3])
        return {
            "probe_enabled": False,
            "peer_observed_movement": True,
            "cadence": cadence,
            "instrumented_cadence": instrumented_cadence,
            "warnings": warnings,
        }
    finally:
        ordinary.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"passed": False, "launches": [], "errors": [], "warnings": []}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=args.chrome, headless=True, args=["--enable-gpu"]
            )
            for enabled in (False, True):
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                if enabled:
                    context.add_init_script("window.mt2ProbeEnabled = true;")
                page = context.new_page()
                page.on("pageerror", lambda error: report["errors"].append(str(error)))
                page.on(
                    "console",
                    lambda message: collect_console(message, report["errors"], report["warnings"]),
                )
                page.goto(args.url, wait_until="domcontentloaded")
                page.wait_for_selector("#status", state="detached", timeout=90000)
                if enabled:
                    page.wait_for_function("!!window.mt2Snapshot", timeout=30000)
                page.wait_for_timeout(2000)
                view = page.evaluate("""() => ({
                    command: typeof window.mt2Command === 'function',
                    snapshot: typeof window.mt2Snapshot === 'string',
                    canvas: document.querySelector('canvas').width > 0
                })""")
                assert view["canvas"], "Game canvas did not initialize"
                assert view["command"] == enabled, "Command bridge activation mismatch"
                assert view["snapshot"] == enabled, "Snapshot activation mismatch"
                report["launches"].append({"enabled": enabled, **view})
                page.screenshot(path=str(args.output / f"enabled-{enabled}.png"))
                page.reload(wait_until="domcontentloaded")
                page.wait_for_selector("#status", state="detached", timeout=90000)
                if enabled:
                    page.wait_for_function("!!window.mt2Snapshot", timeout=30000)
                page.wait_for_timeout(1000)
                assert page.evaluate("typeof window.mt2Command === 'function'") == enabled
                assert page.evaluate("typeof window.mt2Snapshot === 'string'") == enabled
                report["launches"][-1]["reload_verified"] = True
                context.close()
            browser.close()
        assert not report["errors"], "Browser errors occurred"
        report["passed"] = True
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
