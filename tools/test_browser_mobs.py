"""Population evidence from the actual exported clients' subscribed snapshots."""

import math
import statistics
import time
from collections import Counter


def population_summary(web, native, catalog):
    expected = {int(mob["vnum"]) for mob in catalog["mobs"]}
    observed = []
    counts = []
    for snapshot in (web, native):
        ids = {}
        for row in snapshot["monsters"]:
            if int(row["id"]) == 900001:  # Independent authored practice dummy.
                continue
            identity, vnum = int(row["id"]), int(row["definition_vnum"])
            assert identity > 900001 and identity not in ids, "Invalid or duplicate mob ID"
            assert vnum in expected, "Unregistered mob species"
            assert all(math.isfinite(row[key]) for key in ("x", "y", "z")), "Invalid mob position"
            ids[identity] = vnum
        assert len(ids) > 2000, "Expected full original Yongan population"
        assert set(ids.values()) == expected, "Original species missing from subscription"
        observed.append(ids)
        counts.append(dict(sorted(Counter(ids.values()).items())))
    assert observed[0] == observed[1], "Exported clients received different mob populations"
    return {"count": len(observed[0]), "species": len(expected), "species_counts": counts[0]}


def exercise_field(
    page,
    web,
    desktop,
    web_command,
    native_command,
    wait,
    route,
    output,
    *,
    return_to_town=True,
    profile_probe=False,
    field_combat=False,
    ground_items=False,
):
    for snapshot in (web(), desktop()):
        assert snapshot["world_info"] == {
            "map_id": route["map_id"],
            "content_hash": route["map_hash"],
        }
    points = route["waypoints"]

    def arrived(snapshot, point):
        position = snapshot.get("server_position", [])
        return len(position) == 3 and math.dist([position[0], position[2]], point) < 0.25

    def walk(waypoints, label):
        for index, point in enumerate(waypoints):
            web_command("target", x=point[0], z=point[1])
            native_command("target", x=point[0], z=point[1])
            wait(
                f"{label}_{index}",
                lambda point=point: arrived(web(), point) and arrived(desktop(), point),
                15,
            )

    walk(points[1:], "field_route_outward")

    def mobs(snapshot):
        return {
            int(row["row_id"]): row
            for row in snapshot.get("monster_presentations", [])
            if row.get("model_path", "").startswith("res://assets/imported/mobs/")
            and row.get("animation")
            and row.get("pick", {}).get("available")
        }

    wait(
        "both_exports_render_original_field_mobs",
        lambda: bool(mobs(web()).keys() & mobs(desktop()).keys()),
        30,
    )
    page.screenshot(path=str(output / "field-mobs-browser.png"))
    native_command("capture")
    wait("field_native_capture_saved", lambda: (output / "desktop.png").is_file())
    (output / "desktop.png").replace(output / "field-mobs-native.png")
    samples = []
    for _ in range(12):
        page.wait_for_timeout(500)
        a, b = web(), desktop()
        samples.append(
            {
                "time": time.monotonic(),
                "web_fps": a["fps"],
                "native_fps": b["fps"],
                "web_rendered": len(a.get("rendered_monsters", [])),
                "web_npcs": len(a.get("rendered_npcs", [])),
                "native_npcs": len(b.get("rendered_npcs", [])),
                "native_rendered": len(b.get("rendered_monsters", [])),
            }
        )
    result = {
        "web_mobs": mobs(web()),
        "native_mobs": mobs(desktop()),
        "samples": samples,
        "instrumented_web_median_fps": statistics.median(s["web_fps"] for s in samples),
    }
    if profile_probe:
        web_command("profile_performance")
        native_command("profile_performance")
        page.wait_for_timeout(6500)
        wait(
            "both_clients_complete_snapshot_free_profile",
            lambda: all(
                state.get("performance_profile", {}).get("duration_us", 0) >= 5_000_000
                and state["performance_profile"].get("frames", 0) > 0
                and state["performance_profile"].get("snapshot_sampling") is False
                for state in (web(), desktop())
            ),
            15,
        )
        result["snapshot_free_profile"] = {
            "web": web()["performance_profile"],
            "native": desktop()["performance_profile"],
        }
    if field_combat:
        result["combat"] = exercise_field_combat(page, web, desktop, wait, output)
    if ground_items:
        wait(
            "original_ground_models_reach_both_exports",
            lambda: matching_ground_drops(web(), desktop()),
            20,
        )
        result["ground_items"] = {
            "web": web()["drop_presentations"],
            "native": desktop()["drop_presentations"],
        }
        page.screenshot(path=str(output / "ground-items-browser.png"))
    if return_to_town:
        walk(list(reversed(points[:-1])), "field_route_return")
    return result


def exercise_field_combat(page, web, desktop, wait, output):
    """Select a nearby original mob by pointer and hold Space through its death."""
    from test_browser_target import _pick

    state = web()
    # This account scenario creates a Warrior with its original Sword+0 in cell 0.
    sword = next(row for row in state["inventory"] if row["vnum"] == 10)
    if not sword["equipped"]:
        page.keyboard.press("i")
        wait("field_inventory_opens", lambda: web()["ui"]["visible"])
        origin = web()["ui"]["grid_origin"]
        cell = int(sword["cell"])
        page.mouse.click(
            origin[0] + (cell % 5) * 32 + 16,
            origin[1] + (cell % 45 // 5) * 32 + 16,
            button="right",
        )
        wait(
            "field_starter_weapon_equips_and_replicates",
            lambda: (
                any(row["id"] == sword["id"] and row["equipped"] for row in web()["inventory"])
                and all(
                    any(
                        row["character_id"] == state["identity"] and row["weapon_vnum"] == 10
                        for row in snapshot()["appearances"]
                    )
                    for snapshot in (web, desktop)
                )
            ),
        )
        page.keyboard.press("i")
        wait("field_inventory_closes", lambda: not web()["ui"]["visible"])
    state = web()
    position = state["server_position"]
    presentations = {int(row["row_id"]): row for row in state["monster_presentations"]}
    candidates = [
        row
        for row in state["monsters"]
        if int(row["health"]) > 0
        and presentations.get(int(row["id"]), {})
        .get("model_path", "")
        .startswith("res://assets/imported/mobs/")
        and _pick(state, int(row["id"]), int(row["life_sequence"])) is not None
        and math.dist([row["x"], row["z"]], [position[0], position[2]]) < 6.0
    ]
    assert candidates, "Field route has no nearby pickable original mob"
    target = min(
        candidates, key=lambda row: math.dist([row["x"], row["z"]], [position[0], position[2]])
    )
    identity, life, health = int(target["id"]), int(target["life_sequence"]), int(target["health"])

    def monster(snapshot):
        return next((row for row in snapshot["monsters"] if int(row["id"]) == identity), {})

    observed_before = {
        side: max(
            (
                row.get("observed_at_ticks_ms", 0)
                for row in snapshot().get("monster_health_history", [])
            ),
            default=0,
        )
        for side, snapshot in (("web", web), ("native", desktop))
    }

    def observed_damage(dead=False):
        return all(
            health_observed(snapshot(), identity, life, health, observed_before[side], dead=dead)
            for side, snapshot in (("web", web), ("native", desktop))
        )

    point = _pick(state, identity, life)
    page.mouse.click(*point)
    wait(
        "field_pointer_selects_original_mob_life",
        lambda: (
            web().get("combat_target", {}).get("target_id") == identity
            and web()["combat_target"].get("target_life_sequence") == life
        ),
    )
    page.keyboard.down("Space")
    try:
        wait(
            "field_damage_replicates_to_both_exports",
            observed_damage,
            20,
        )
        wait(
            "field_death_replicates_to_both_exports",
            lambda: observed_damage(dead=True),
            30,
        )
    finally:
        page.keyboard.up("Space")
    after = {"web": monster(web()), "native": monster(desktop())}
    page.screenshot(path=str(output / "field-combat-browser.png"))
    return {
        "before": target,
        "after": after,
        "pointer": point,
        "health_events": {
            side: [
                row
                for row in snapshot().get("monster_health_history", [])
                if row["id"] == identity
                and row["life_sequence"] == life
                and row["observed_at_ticks_ms"] > observed_before[side]
            ]
            for side, snapshot in (("web", web), ("native", desktop))
        },
    }


def health_observed(snapshot, identity, life, health, after_ticks, *, dead=False):
    """Keep short-lived corpse evidence across independently delayed subscriptions."""
    return any(
        row.get("id") == identity
        and row.get("life_sequence") == life
        and row.get("observed_at_ticks_ms", 0) > after_ticks
        and (row.get("health") == 0 if dead else 0 <= row.get("health", health) < health)
        for row in snapshot.get("monster_health_history", [])
    )


def matching_ground_drops(web, native):
    """Match rendered original ground models to the browser player's public drops."""
    owned = set()
    for table, item_mode in (("loot", False), ("item_drops", True)):
        for row in web.get(table, []):
            if row.get("owner") == web.get("identity"):
                owned.add((item_mode, int(row["id"])))
    views = []
    for snapshot in (web, native):
        views.append(
            {
                (bool(row["item"]), int(row["row_id"])): (row["ground_model_path"], row["label"])
                for row in snapshot.get("drop_presentations", [])
                if row.get("ground_model_path", "").startswith(
                    "res://assets/imported/ground_items/models/"
                )
            }
        )
    return bool(owned) and all(
        key in views[0] and key in views[1] and views[0][key] == views[1][key] for key in owned
    )
