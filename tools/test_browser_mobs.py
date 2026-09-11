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
        # The catalog is the set of possible species. Original regeneration
        # chooses group variants and can fail terrain placement; a live census
        # need not contain every catalog member simultaneously.
        observed.append(ids)
        counts.append(dict(sorted(Counter(ids.values()).items())))
    assert observed[0] == observed[1], "Exported clients received different mob populations"
    return {
        "count": len(observed[0]),
        "species": len(counts[0]),
        "catalog_species": len(expected),
        "unobserved_species": sorted(expected - counts[0].keys()),
        "species_counts": counts[0],
    }


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
    evidence=None,
):
    # Keep completed field evidence available if a later return/lifecycle step fails.
    result = evidence if evidence is not None else {}
    for snapshot in (web(), desktop()):
        assert snapshot["world_info"] == {
            "map_id": route["map_id"],
            "content_hash": route["map_hash"],
        }
    points = route["waypoints"]

    def arrived(snapshot, point):
        position = snapshot.get("server_position", [])
        return len(position) == 3 and math.dist([position[0], position[2]], point) < 0.25

    def walk(waypoints, label, timeout=60):
        for index, point in enumerate(waypoints):
            web_command("target", x=point[0], z=point[1])
            native_command("target", x=point[0], z=point[1])
            wait(
                f"{label}_{index}",
                lambda point=point: arrived(web(), point) and arrived(desktop(), point),
                timeout,
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
    result.update(
        {
            "web_mobs": mobs(web()),
            "native_mobs": mobs(desktop()),
            "samples": samples,
            "instrumented_web_median_fps": statistics.median(s["web_fps"] for s in samples),
        }
    )
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
        result["combat"] = exercise_field_combat(
            page, web, desktop, wait, output, web_command, native_command
        )
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
        native_command("capture")
        wait("ground_native_capture_saved", lambda: (output / "desktop.png").is_file())
        (output / "desktop.png").replace(output / "ground-items-native.png")
    if return_to_town:
        result["return_walk"] = walk_field_return(
            web, desktop, web_command, native_command, wait, points
        )
    return result


def walk_field_return(web, desktop, web_command, native_command, wait, points):
    """Return along the authored route with a per-client defeat outcome.

    The route ends inside an original mixed mob pack, so a low-level character
    can legitimately be killed while retreating and respawn at the authored
    town spawn instead of walking the remaining legs. A client only stops
    having to reach the remaining waypoints after the server itself reports the
    defeat: a zero health row, a defeat rejection or a respawned life
    generation. Movement intents then stop for that client, the other client
    still has to arrive at every waypoint, at least one client has to walk the
    complete return route, and both clients have to finish at the spawn.
    """
    spawn = points[0]
    legs = list(reversed(points[:-1]))
    readers = {"web": web, "native": desktop}
    writers = {"web": web_command, "native": native_command}

    def own_row(snapshot):
        identity = snapshot.get("identity")
        return next(
            (row for row in snapshot.get("player_rows", []) if row.get("identity") == identity),
            {},
        )

    def defeat_evidence(snapshot, base_life):
        row = own_row(snapshot)
        if row:
            if int(row.get("health", 1)) == 0:
                return "zero_health"
            if int(row.get("life_sequence", 0)) > base_life:
                return "respawned_life_sequence"
        return next(
            (
                str(message)
                for message in snapshot.get("errors", [])
                if "defeated" in str(message).lower()
            ),
            "",
        )

    def at_point(snapshot, point):
        position = snapshot.get("server_position", [])
        return len(position) == 3 and math.dist([position[0], position[2]], point) < 0.25

    base_life = {
        side: int(own_row(read()).get("life_sequence", 0)) for side, read in readers.items()
    }
    defeats: dict[str, dict] = {}
    covered: dict[str, set] = {side: set() for side in readers}

    def leg_status(side, point, leg):
        snapshot = readers[side]()
        if side not in defeats:
            evidence = defeat_evidence(snapshot, base_life[side])
            if evidence:
                defeats[side] = {
                    "leg": leg,
                    "evidence": evidence,
                    "health": int(own_row(snapshot).get("health", -1)),
                    "life_sequence": int(own_row(snapshot).get("life_sequence", 0)),
                    "server_position": snapshot.get("server_position"),
                }
        if at_point(snapshot, point):
            covered[side].add(leg)
            return True
        return side in defeats

    for leg, point in enumerate(legs):
        for side, command in writers.items():
            if side not in defeats:
                command("target", x=point[0], z=point[1])
        wait(
            f"field_route_return_{leg}",
            lambda point=point, leg=leg: all(leg_status(side, point, leg) for side in readers),
            60,
        )

    walked = [side for side, seen in covered.items() if seen == set(range(len(legs)))]
    assert walked, "No exported client walked every authored return leg: " + repr(
        {side: sorted(seen) for side, seen in covered.items()}
    )
    wait("field_route_return_one_export_walked_every_leg", lambda: True)
    wait(
        "field_route_return_both_exports_at_authored_spawn",
        lambda: all(at_point(read(), spawn) for read in readers.values()),
        30,
    )
    for side in sorted(defeats):
        wait(
            f"field_route_return_{side}_defeated_in_field_and_respawned",
            lambda side=side: int(own_row(readers[side]()).get("health", 0)) > 0,
            30,
        )
    return {
        "legs": len(legs),
        "covered": {side: sorted(seen) for side, seen in covered.items()},
        "defeats": defeats,
        "final": {side: read().get("server_position") for side, read in readers.items()},
    }


def exercise_field_combat(page, web, desktop, wait, output, web_command, native_command):
    """Walk onto the nearest original mob, then hold Space through its death."""
    from test_browser_target import _pick

    def settled_world():
        """The browser's world view outside its scheduled session refresh.

        Both exports refresh their signed session every four minutes and replay
        their subscriptions afterwards. A bare read inside that window drains
        the inventory and the population, so field entry waits for a settled
        world instead of treating the refresh as a product failure.
        """
        snapshot = web()
        if (
            snapshot.get("connection_state") == "connected"
            and snapshot.get("identity")
            and len(snapshot.get("monsters", [])) > 100
        ):
            return snapshot
        return {}

    settled: dict = {}

    def starter_weapon_ready():
        snapshot = settled_world()
        if not snapshot:
            return False
        sword = next(
            (row for row in snapshot.get("inventory", []) if int(row.get("vnum", 0)) == 10),
            None,
        )
        if sword is None:
            return False
        settled["sword_state"] = snapshot
        settled["sword"] = sword
        return True

    wait("field_combat_subscription_settled_with_original_weapon", starter_weapon_ready, 90)
    state = settled["sword_state"]
    identity = state["identity"]
    # This account scenario creates a Warrior with its original Sword+0 in cell 0.
    sword = settled["sword"]

    def press_inventory(check: str, expected: bool, timeout: float = 120) -> None:
        """Toggle the original inventory while tolerating a session refresh.

        Both exports refresh their signed session every four minutes and replay
        their subscriptions afterwards. A key press that lands in that window
        is swallowed even though the canvas still owns DOM focus (verified with
        an isolated CDP focus probe), so wait for a settled world, focus the
        canvas and re-send a bounded number of times instead of treating a lost
        key press as a product failure.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if bool(web()["ui"]["visible"]) is expected:
                break
            if not settled_world():
                time.sleep(0.5)
                continue
            page.bring_to_front()
            page.locator("canvas").focus()
            page.keyboard.press("i")
            attempt_deadline = time.monotonic() + 8
            while time.monotonic() < attempt_deadline:
                if bool(web()["ui"]["visible"]) is expected:
                    break
                time.sleep(0.2)
        wait(check, lambda: bool(web()["ui"]["visible"]) is expected, 30)

    if not sword["equipped"]:
        press_inventory("field_inventory_opens", True)
        cell = int(sword["cell"])
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if any(row["id"] == sword["id"] and row["equipped"] for row in web()["inventory"]):
                break
            if not settled_world():
                time.sleep(0.5)
                continue
            state = web()
            if not state["ui"]["visible"]:
                page.bring_to_front()
                page.locator("canvas").focus()
                page.keyboard.press("i")
                time.sleep(1.0)
                continue
            origin = state["ui"]["grid_origin"]
            point = [
                origin[0] + (cell % 5) * 32 + 16,
                origin[1] + (cell % 45 // 5) * 32 + 16,
            ]
            # ClassicSlot only arms on a real mouse-enter edge: enter from
            # outside the window and keep intermediate motion events, exactly
            # like the accepted inventory harness. A click sent while the
            # pointer was already parked on the cell (or while the client
            # rebuilt its rows after the four-minute session refresh) is
            # delivered but never hits the slot.
            page.bring_to_front()
            page.mouse.move(state["ui"]["window_rect"][0] - 8, point[1])
            page.mouse.move(point[0], point[1], steps=6)
            page.mouse.click(point[0], point[1], button="right")
            time.sleep(1.0)
        wait(
            "field_starter_weapon_equips_and_replicates",
            lambda: (
                any(row["id"] == sword["id"] and row["equipped"] for row in web()["inventory"])
                and all(
                    any(
                        row["character_id"] == identity and row["weapon_vnum"] == 10
                        for row in snapshot()["appearances"]
                    )
                    for snapshot in (web, desktop)
                )
            ),
        )
        press_inventory("field_inventory_closes", False)

    def settled_field_state():
        snapshot = settled_world()
        if snapshot:
            settled["field_state"] = snapshot
            return True
        return False

    wait("field_combat_field_population_settled", settled_field_state, 90)

    def original_mobs(snapshot, radius):
        """Pickable imported mobs inside *radius*, nearest first."""
        position = snapshot["server_position"]
        presentations = {int(row["row_id"]): row for row in snapshot["monster_presentations"]}
        found = []
        for row in snapshot["monsters"]:
            if int(row["health"]) <= 0:
                continue
            presentation = presentations.get(int(row["id"]), {})
            if not presentation.get("model_path", "").startswith("res://assets/imported/mobs/"):
                continue
            if _pick(snapshot, int(row["id"]), int(row["life_sequence"])) is None:
                continue
            distance = math.dist([row["x"], row["z"]], [position[0], position[2]])
            if distance < radius:
                found.append((distance, row))
        return sorted(found, key=lambda item: item[0])

    def both_arrived(point):
        for snapshot in (web(), desktop()):
            position = snapshot.get("server_position", [])
            if len(position) != 3 or math.dist([position[0], position[2]], point) >= 0.25:
                return False
        return True

    # Original area regeneration samples its own placement, so the authored
    # route can end several metres outside a pack on an unlucky roll. Walk the
    # final metres to the nearest pickable original mob instead of requiring the
    # roll to land inside the accept radius.
    approach = original_mobs(settled["field_state"], 60.0)
    assert approach, "Field route has no pickable original mob within approach range"
    for step in range(4):
        if approach[0][0] < 3.0:
            break
        position = web().get("server_position", [0.0, 0.0, 0.0])
        target = approach[0][1]
        dx, dz = position[0] - target["x"], position[2] - target["z"]
        length = math.hypot(dx, dz)
        if length < 0.5:
            break
        stand = (target["x"] + dx / length * 2.2, target["z"] + dz / length * 2.2)
        web_command("target", x=stand[0], z=stand[1])
        native_command("target", x=stand[0], z=stand[1])
        wait(f"field_approach_original_mob_{step}", lambda point=stand: both_arrived(point), 60)
        settled["field_state"] = {}
        wait("field_population_resettled_after_approach", settled_field_state, 90)
        approach = original_mobs(settled["field_state"], 60.0)

    state = settled["field_state"]
    position = state["server_position"]
    candidates = [row for distance, row in approach if distance < 6.0]
    assert candidates, "Field route has no nearby pickable original mob"
    target = min(
        candidates,
        key=lambda row: math.dist([row["x"], row["z"]], [position[0], position[2]]),
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
