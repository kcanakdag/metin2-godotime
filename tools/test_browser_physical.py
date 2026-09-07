"""Check physical stat projections through the exported Web and Linux item UI."""

from __future__ import annotations

import json
from pathlib import Path

from test_browser_actors import rendered_actor


def exercise_physical(page, web, desktop, native_command, wait, web_id, native_id, output):
    """Equip/unequip with real UI events; inspect private rows and rendered labels."""
    definitions = json.loads(
        (
            Path(__file__).resolve().parents[1] / "server/content/p0-warrior-dog/actions.v1.json"
        ).read_text()
    )
    expected_hash = definitions["gameplay_definition_hash"]
    wait(
        "physical_both_exports_use_current_definitions",
        lambda: web().get("definition_hash") == desktop().get("definition_hash") == expected_hash,
    )
    evidence = {"definition_hash": expected_hash, "sides": {}}
    for side, snapshot, peer, identity, peer_id in (
        ("web", web, desktop, web_id, native_id),
        ("native", desktop, web, native_id, web_id),
    ):
        evidence["sides"][side] = _exercise_side(
            page, snapshot, peer, native_command, wait, side, identity, peer_id, output
        )
    return evidence


def _exercise_side(page, snapshot, peer, native_command, wait, side, identity, peer_id, output):
    def ui():
        return snapshot()["ui"]

    def sword():
        return next(row for row in snapshot()["inventory"] if row["vnum"] == 10)

    def click(point, right=False):
        if side == "web":
            page.mouse.click(*point, button="right" if right else "left")
        else:
            native_command(
                "pointer_right_click" if right else "pointer_click", x=point[0], y=point[1]
            )

    def move(point):
        if side == "web":
            page.mouse.move(*point, steps=6)
        else:
            native_command("pointer_move", x=point[0], y=point[1])

    def inventory():
        if side == "web":
            page.keyboard.press("i")
        else:
            native_command("inventory")

    def capture(label):
        destination = output / f"physical-{side}-{label}.png"
        if side == "web":
            page.screenshot(path=str(destination))
        else:
            pending = output / "desktop.png"
            pending.unlink(missing_ok=True)
            native_command("capture")
            wait(f"physical_{side}_{label}_capture", pending.is_file)
            pending.replace(destination)

    def matches(equipped):
        state, remote = snapshot(), peer()
        own = next(row for row in state["progression"] if row["character_id"] == identity)
        values = state["ui"]["status"]["values"]
        minimum, maximum = (28, 31) if equipped else (10, 10)
        actors = [rendered_actor(state, identity), rendered_actor(remote, identity)]
        return (
            own.get("display_attack_min") == minimum
            and own.get("display_attack_max") == maximum
            and own.get("display_defense") == 5
            and values.get("attack") == ("28-31" if equipped else "10")
            and values.get("defense") == "5"
            and all(row["character_id"] == identity for row in state["progression"])
            and all(row["character_id"] == peer_id for row in remote["progression"])
            and all(
                row.get("weapon_vnum") == (10 if equipped else 0)
                and bool(row.get("equipment_attached")) == equipped
                and not row.get("error")
                for row in actors
            )
        )

    original = sword().copy()
    assert not original["equipped"] and original["cell"] == 0
    click(ui()["taskbar"]["character_center"])
    wait(f"physical_{side}_status_opens", lambda: ui()["status"]["visible"])
    wait(f"physical_{side}_unarmed_stats_and_privacy", lambda: matches(False))
    inventory()
    wait(f"physical_{side}_inventory_opens", lambda: ui()["visible"])
    origin = ui()["grid_origin"]
    point = [origin[0] + 16, origin[1] + 16]
    if side == "web":
        move([ui()["window_rect"][0] - 8, point[1]])
    # Native cursor is still at the taskbar button, outside the inventory.
    move(point)
    wait(f"physical_{side}_sword_tooltip_visible", lambda: ui()["tooltip_visible"])
    capture("unarmed-tooltip")
    click(point, right=True)
    wait(f"physical_{side}_equipped_stats_and_peer_attachment", lambda: matches(True))
    capture("equipped-status")
    equipped = snapshot()
    origin = ui()["equipment_origin"]
    click([origin[0] + 16, origin[1] + 16], right=True)
    wait(
        f"physical_{side}_unequip_restores_stats_and_item",
        lambda: matches(False) and sword() == original,
    )
    evidence = {"equipped": equipped, "restored": snapshot()}
    inventory()
    wait(f"physical_{side}_inventory_closes", lambda: not ui()["visible"])
    click(ui()["taskbar"]["character_center"])
    wait(f"physical_{side}_status_closes", lambda: not ui()["status"]["visible"])
    return evidence
