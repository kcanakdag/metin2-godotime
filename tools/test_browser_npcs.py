"""Walk both authenticated exported clients to an original stationary NPC."""

import math


def npc(snapshot, spawn_id):
    rows = snapshot.get("rendered_npcs", [])
    matches = [row for row in rows if row["spawn_id"] == spawn_id]
    assert len(matches) <= 1, "Duplicate NPC presentation after map entry"
    return matches[0] if matches else {}


def population_matches(snapshot, expected):
    for definition in expected:
        actual = npc(snapshot, definition["spawn_id"])
        if (
            not actual.get("playing")
            or not actual.get("idle")
            or actual.get("name") != definition["name"]
            or len(actual.get("position", [])) != 3
            or not all(math.isfinite(v) for v in actual["position"])
            or math.dist(actual["position"], definition["position"]) > 0.02
        ):
            return False
        angle = actual.get("yaw", math.nan) - definition["yaw"]
        if not math.isfinite(angle) or abs(math.atan2(math.sin(angle), math.cos(angle))) > 0.0001:
            return False
    return True


def area_population_matches(first, second, areas):
    for area in areas:
        a, b = (npc(snapshot, area["spawn_id"]) for snapshot in (first, second))
        bounds = area["bounds_cm"]
        for row in (a, b):
            position = row.get("position", [])
            if (
                not row.get("playing")
                or not row.get("idle")
                or row.get("name") != area["name"]
                or len(position) != 3
                or not all(math.isfinite(v) for v in position)
                or not bounds[0] - 0.01 <= position[0] * 100 <= bounds[2] + 0.01
                or not bounds[1] - 0.01 <= position[2] * 100 <= bounds[3] + 0.01
                or not math.isfinite(row.get("yaw", math.nan))
            ):
                return False
        if math.dist(a["position"], b["position"]) > 0.001:
            return False
        angle = a["yaw"] - b["yaw"]
        if abs(math.atan2(math.sin(angle), math.cos(angle))) > 0.0001:
            return False
    return True


def exercise_npcs(page, web, desktop, web_command, native_command, wait, route, output):
    spawn_id = route["spawn_id"]
    expected = route["npc_position"]
    population = route.get("entry_population", [])
    areas = route.get("entry_areas", [])
    if areas:
        wait(
            f"both_exports_render_{len(areas)}_area_npcs_at_matching_server_positions",
            lambda: area_population_matches(web(), desktop(), areas),
        )
    if population:
        wait(
            f"both_exports_render_{len(population)}_original_entry_npcs",
            lambda: all(population_matches(s, population) for s in (web(), desktop())),
        )
        page.screenshot(path=str(output / "town-entry-browser.png"))
    for snapshot in (web(), desktop()):
        assert snapshot["world_info"] == {
            "map_id": route["map_id"],
            "content_hash": route["map_hash"],
        }, "NPC walking fixture differs from the subscribed server map"
        assert sum(row.get("definition_vnum") == 101 for row in snapshot["monsters"]) == 6, (
            "Expected the six-dog population database"
        )
    wait(
        "both_exports_render_one_guard_at_original_position",
        lambda: all(
            npc(state, spawn_id).get("playing")
            and math.dist(npc(state, spawn_id)["position"], expected) < 0.01
            for state in (web(), desktop())
        ),
    )

    def arrived(snapshot, point):
        position = snapshot.get("server_position", [])
        return len(position) == 3 and math.dist([position[0], position[2]], point) < 0.15

    for index, point in enumerate(route["waypoints"][1:]):
        web_command("target", x=point[0], z=point[1])
        native_command("target", x=point[0], z=point[1])
        wait(
            f"both_clients_walk_validated_guard_route_{index + 1}",
            lambda point=point: arrived(web(), point) and arrived(desktop(), point),
            15,
        )
    point = route["native_final"]
    native_command("target", x=point[0], z=point[1])
    wait("native_stands_beside_browser_at_guard", lambda: arrived(desktop(), point), 8)
    web_command("stop")
    native_command("stop")
    wait(
        "guard_visible_and_animating_in_both_exported_cameras",
        lambda: all(
            npc(state, spawn_id).get("in_view") and npc(state, spawn_id).get("playing")
            for state in (web(), desktop())
        ),
    )
    before = {"web": npc(web(), spawn_id), "native": npc(desktop(), spawn_id)}
    page.screenshot(path=str(output / "world-npc-browser.png"))
    (output / "desktop.png").unlink(missing_ok=True)
    native_command("capture")
    wait("native_guard_render_capture_saved", lambda: (output / "desktop.png").is_file())
    (output / "desktop.png").replace(output / "world-npc-native.png")
    # Both clients use the production ray-picking and approach path.
    page.mouse.move(*before["web"]["screen"])
    wait(
        "guard_hover_is_distinct_from_combat",
        lambda: web().get("hover_npc") == spawn_id and not web().get("hover_target"),
    )
    start_position = web()["server_position"]
    page.mouse.click(*before["web"]["screen"])
    wait(
        "browser_approaches_and_receives_private_dialogue",
        lambda: (
            web().get("npc_panel", {}).get("visible")
            and web().get("npc_interaction", {}).get("spawn_id") == spawn_id
        ),
    )
    assert math.dist(web()["server_position"], start_position) > 0.2, (
        "Click did not exercise auto-approach"
    )
    assert not desktop().get("npc_interaction"), "Other account received a private conversation"
    assert not web().get("combat_target"), "NPC became a combat target"
    point = npc(desktop(), spawn_id)["screen"]
    native_command("pointer_click", x=point[0], y=point[1])
    wait(
        "native_click_opens_independent_dialogue",
        lambda: desktop().get("npc_panel", {}).get("visible"),
    )
    assert web()["npc_interaction"]["session_id"] != desktop()["npc_interaction"]["session_id"]
    page.screenshot(path=str(output / "npc-dialogue-browser.png"))
    native_command("capture")
    wait("native_dialogue_capture_saved", lambda: (output / "desktop.png").is_file())
    (output / "desktop.png").replace(output / "npc-dialogue-native.png")
    page.mouse.click(*web()["npc_panel"]["close_center"])
    wait(
        "browser_close_button_closes_exact_session",
        lambda: not web().get("npc_interaction") and not web()["npc_panel"]["visible"],
    )
    point = desktop()["npc_panel"]["close_center"]
    native_command("pointer_click", x=point[0], y=point[1])
    wait(
        "native_close_button_closes_exact_session",
        lambda: not desktop().get("npc_interaction") and not desktop()["npc_panel"]["visible"],
    )
    page.mouse.click(*npc(web(), spawn_id)["screen"])
    wait("browser_can_reopen_after_close", lambda: web()["npc_panel"]["visible"])
    page.keyboard.press("Escape")
    wait("escape_closes_conversation", lambda: not web()["npc_panel"]["visible"])
    page.mouse.click(*npc(web(), spawn_id)["screen"])
    wait("browser_reopens_before_movement", lambda: web()["npc_panel"]["visible"])
    position = web()["server_position"]
    page.keyboard.down("KeyD")
    try:
        wait(
            "WASD_after_dialogue_moves_and_closes_session",
            lambda: (
                not web().get("npc_interaction")
                and math.dist(web()["server_position"], position) > 0.5
            ),
        )
    finally:
        page.keyboard.up("KeyD")
    web_command("stop")
    if population:
        wait(
            "town_population_preserved_after_guard_route_and_dialogue",
            lambda: all(population_matches(s, population) for s in (web(), desktop())),
        )
    return before
