"""Walk both authenticated exported clients to an original stationary NPC."""

import json
import math
import time

# Pinned original `config.cpp` VIEW_RANGE plus the client's Manhattan-style
# approximation in `client/scripts/world/pve_visibility.gd`. The entry walk
# re-derives which authored town NPCs a correct export may instantiate instead
# of freezing a hand-picked list: two Yongan placements sit at 101.7% and 102.8%
# of the cutoff, so a hard-coded expectation would fail on a legitimate spawn or
# geometry change while proving nothing about the pinned range.
VIEW_RANGE_CM = 5500


def view_distance_cm(position, viewer):
    """Pinned presentation distance in centimetres, truncated as the client does."""
    dx = abs(int(position[0] * 100.0) - int(viewer[0] * 100.0))
    dz = abs(int(position[2] * 100.0) - int(viewer[2] * 100.0))
    return (246 * max(dx, dz) + 102 * min(dx, dz)) >> 8


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


def quest_state(snapshot, quest_id):
    rows = [row for row in snapshot.get("quest_states", []) if row.get("quest_id") == quest_id]
    assert len(rows) <= 1, "Duplicate quest state row for " + quest_id
    return rows[0] if rows else {}


def pinned_entry_selection(snapshot, definitions):
    """Classify authored town NPCs, or None while the snapshot is unusable."""
    if not world_session_settled(snapshot):
        return None
    viewer = snapshot.get("server_position", [])
    if len(viewer) != 3 or not all(math.isfinite(value) for value in viewer):
        return None
    rendered = {row["spawn_id"]: row for row in snapshot.get("rendered_npcs", [])}
    visible = []
    hidden = []
    for definition in definitions:
        if view_distance_cm(definition["position"], viewer) <= VIEW_RANGE_CM:
            visible.append(definition)
        else:
            hidden.append(definition)
    return rendered, visible, hidden


def pinned_entry_presentation_matches(snapshot, definitions, areas):
    """Every authored town NPC must follow the pinned original view range.

    In-range placements render with their compiled name, position and yaw;
    out-of-range placements and all six wandering area NPCs must not be
    instantiated at all. The expected split is derived from the settled position
    so the invariant under test is the pinned range, not a frozen list.
    """
    selection = pinned_entry_selection(snapshot, definitions)
    if selection is None:
        return False
    rendered, visible, hidden = selection
    if not visible:
        return False
    for definition in hidden:
        if definition["spawn_id"] in rendered:
            return False
    for definition in visible:
        if not population_matches(snapshot, [definition]):
            return False
    return all(area["spawn_id"] not in rendered for area in areas)


def quest_objective(snapshot, quest_id):
    rows = [row for row in snapshot.get("quest_objectives", []) if row.get("quest_id") == quest_id]
    assert len(rows) <= 1, "Duplicate quest objective row for " + quest_id
    return rows[0] if rows else {}


def tracked_letter(snapshot, quest_id):
    return str(quest_objective(snapshot, quest_id).get("letter_title", "")).strip()


def quest_signature(snapshot):
    """Every externally visible quest field, for cross-account leak checks.

    Comparing a full signature against the account's own baseline is stronger
    than asserting a literal starting state: it catches a leak into any quest or
    objective field, and it stays correct when the opening catalog is retuned.
    """
    states = {
        row.get("quest_id"): (row.get("sequence"), row.get("state"), row.get("title"))
        for row in snapshot.get("quest_states", [])
    }
    objectives = {
        row.get("quest_id"): (
            row.get("label"),
            row.get("letter_title"),
            row.get("target_vnum"),
            row.get("amount"),
            row.get("total"),
        )
        for row in snapshot.get("quest_objectives", [])
    }
    return states, objectives


def replay_stable_signature(snapshot):
    """Quest fields that neither a session refresh nor a relog can rewrite.

    Every character owns a row for every catalog quest, and `sequence` counts
    how often a state was (re-)entered. A scheduled refresh re-authenticates,
    replays the world subscription and re-fires the quest login triggers, so a
    state with a `login` trigger legitimately advances its sequence during a
    run. Comparing a raw signature across that replay therefore fails on a
    correct server. The visible state, the tracked letter and the objective
    counters are what another account's private hand-in would overwrite, so
    those are compared exactly and `sequence` is left out.
    """
    states, objectives = quest_signature(snapshot)
    return {
        "states": {quest_id: row[1:] for quest_id, row in states.items()},
        "objectives": objectives,
    }


def world_session_settled(snapshot):
    """True only for a client that finished entering or re-entering the world.

    Both exports refresh their signed session on a timer; the refresh drops the
    world connection, re-authenticates and replays the world subscription. While
    that runs the probe still answers, but with `connection_state ==
    "subscribing"`, an empty `world_info` and no private rows. Every cross-account
    baseline and comparison therefore has to wait for the replay first: an empty
    snapshot would otherwise look like a leaked, missing or unchanged account.
    """
    return snapshot.get("connection_state") == "connected" and bool(
        snapshot.get("world_info", {}).get("map_id")
    )


def own_quest_rows_complete(snapshot, spawn_id):
    """True only for an idle account whose own rows finished replaying.

    `world_info` and the rendered population return before the private quest
    rows on some replays, so a settled session alone can still expose a
    half-applied opening catalog. Requiring every seeded quest to be present
    keeps a truncated snapshot from becoming a baseline that can never be met
    again.
    """
    seeded = ("main_quest_lv1", "main_quest_lv2", "main_quest_lv3", "find_squareguard")
    if not world_session_settled(snapshot):
        return False
    if any(not quest_state(snapshot, quest_id) for quest_id in seeded):
        return False
    return bool(npc(snapshot, spawn_id).get("screen"))


def settled_guard_screen(snapshot, spawn_id):
    """The guard's projected point, but only from a session that is in the world."""
    if not world_session_settled(snapshot):
        return []
    return npc(snapshot, spawn_id).get("screen") or []


def settled_position(snapshot):
    """The authoritative position, but only from a session that is in the world."""
    if not world_session_settled(snapshot):
        return []
    position = snapshot.get("server_position", [])
    return position if len(position) == 3 else []


def exercise_npcs(page, web, desktop, web_command, native_command, wait, route, output):
    spawn_id = route["spawn_id"]
    expected = route["npc_position"]
    population = route.get("entry_population", [])
    areas = route.get("areas_outside_entry_view", [])

    def settled_web_field(label, read, timeout=120):
        """Read one browser field without ever landing inside a session refresh.

        Both exports refresh their signed session on a timer; the refresh drops
        the world subscription, so NPC rows, the position and the dialogue panel
        disappear for a few seconds. Waiting and then re-reading would race that
        window, so the value comes from the same settled snapshot the wait saw.
        """
        wait(label, lambda: bool(world_session_settled(web()) and read(web())), timeout)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snapshot = web()
            if world_session_settled(snapshot):
                value = read(snapshot)
                if value:
                    return value
            time.sleep(0.1)
        raise AssertionError(label + " lost its settled browser state")

    def settled_web_guard_screen(label, timeout=120):
        return settled_web_field(
            label, lambda snapshot: settled_guard_screen(snapshot, spawn_id), timeout
        )

    def settled_web_position(label, timeout=120):
        return settled_web_field(label, settled_position, timeout)

    def reopen_guard_dialogue(check, point_check):
        """Click the guard and prove its dialogue reopens, or explain the refusal.

        World clicks are delivered through `_unhandled_input`, so a GUI control
        with a mouse filter of STOP silently eats them. When the click does not
        open a session this records the pointer-blocking control, the reducer
        tail and the probe publication counters instead of only timing out.
        """
        before = web()
        point = settled_web_guard_screen(point_check)
        page.mouse.click(*point)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if web().get("npc_panel", {}).get("visible"):
                # ``wait`` is owned by the caller, so it appends this check to
                # the run's list and prints the same PASS line. This module has
                # no ``checks`` of its own; referencing one aborted the run
                # after the reopen had already succeeded.
                wait(check, lambda: True)
                return
            time.sleep(0.1)
        after = web()
        diagnostics = {
            "check": check,
            "spawn_id": spawn_id,
            "click_point": [round(float(value), 3) for value in point],
            "hovered_control_before": before.get("hovered_control", ""),
            "hovered_control_after": after.get("hovered_control", ""),
            "mouse_position_after": after.get("mouse_position", []),
            "hover_npc_before": before.get("hover_npc", ""),
            "hover_npc_after": after.get("hover_npc", ""),
            "server_position_before": before.get("server_position", []),
            "server_position_after": after.get("server_position", []),
            "snapshot_seq_before": before.get("snapshot_seq"),
            "snapshot_seq_after": after.get("snapshot_seq"),
            "npc_interaction_after": after.get("npc_interaction", {}),
            "request_timings_before": before.get("request_timings", []),
            "request_timings_after": after.get("request_timings", []),
            "errors": after.get("errors", []),
        }
        (output / f"{check}-diagnostics.json").write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True) + "\n"
        )
        raise AssertionError(
            "%s timed out: hovered_control=%r hover_npc=%r snapshot_seq=%r->%r"
            % (
                check,
                diagnostics["hovered_control_after"],
                diagnostics["hover_npc_after"],
                diagnostics["snapshot_seq_before"],
                diagnostics["snapshot_seq_after"],
            )
        )

    if population:
        wait(
            "both_exports_present_the_pinned_original_entry_selection",
            lambda: all(
                pinned_entry_presentation_matches(state, population, areas)
                for state in (web(), desktop())
            ),
        )
        selection = pinned_entry_selection(web(), population)
        if selection is not None:
            _, visible, hidden = selection
            (output / "entry-view-selection.json").write_text(
                json.dumps(
                    {
                        "view_range_cm": VIEW_RANGE_CM,
                        "viewer": web().get("server_position", []),
                        "visible": [definition["spawn_id"] for definition in visible],
                        "hidden_placements": [definition["spawn_id"] for definition in hidden],
                        "hidden_areas": [area["spawn_id"] for area in areas],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        page.screenshot(path=str(output / "town-entry-browser.png"))
    for snapshot in (web(), desktop()):
        assert snapshot["world_info"] == {
            "map_id": route["map_id"],
            "content_hash": route["map_hash"],
        }, "NPC walking fixture differs from the subscribed server map"
    # The guard stands about 105 m from the entry point while the pinned original
    # VIEW_RANGE is 55 m, so a correct client must not present it yet. Rendering
    # it on entry would mean the export ignored the original presentation range.
    for state in (web(), desktop()):
        assert not npc(state, spawn_id), "Guard rendered outside the pinned view range"

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
        "guard_rendered_at_original_position_in_both_exported_cameras",
        lambda: all(
            npc(state, spawn_id).get("in_view")
            and npc(state, spawn_id).get("playing")
            and math.dist(npc(state, spawn_id)["position"], expected) < 0.01
            for state in (web(), desktop())
        ),
    )
    # Baseline the idle account's quest state only while both clients are fully
    # in the world, so a refresh replay cannot be frozen in as the baseline. The
    # positive expectations keep the baseline from being vacuously empty.
    wait(
        "both_accounts_are_settled_and_track_the_guard_letter",
        lambda: (
            world_session_settled(web())
            and world_session_settled(desktop())
            and quest_state(desktop(), "main_quest_lv1").get("state") == "gototeacher"
            and bool(npc(desktop(), spawn_id).get("screen"))
        ),
        120,
    )
    before = {"web": npc(web(), spawn_id), "native": npc(desktop(), spawn_id)}
    hover_point = settled_web_guard_screen("browser_guard_renders_before_hover")
    # The idle baseline is one settled, fully replayed snapshot of the account's
    # own rows, taken from the same read the wait accepted.
    deadline = time.monotonic() + 120
    while True:
        desktop_baseline_snapshot = desktop()
        if own_quest_rows_complete(desktop_baseline_snapshot, spawn_id):
            break
        if time.monotonic() > deadline:
            raise AssertionError("idle_account_quest_baseline never fully replayed")
        time.sleep(0.1)
    desktop_quests_before = replay_stable_signature(desktop_baseline_snapshot)
    (output / "idle-quests-before.json").write_text(
        json.dumps(
            {
                "full": quest_signature(desktop_baseline_snapshot),
                "replay_stable": desktop_quests_before,
            }
        ),
        encoding="utf-8",
    )
    page.screenshot(path=str(output / "world-npc-browser.png"))
    (output / "desktop.png").unlink(missing_ok=True)
    native_command("capture")
    wait("native_guard_render_capture_saved", lambda: (output / "desktop.png").is_file())
    (output / "desktop.png").replace(output / "world-npc-native.png")
    wait(
        "both_accounts_track_their_own_level_one_guard_letter",
        lambda: all(
            quest_state(state, "main_quest_lv1").get("state") == "gototeacher"
            and tracked_letter(state, "main_quest_lv1") == "Welcome to Metin2"
            and quest_objective(state, "main_quest_lv1").get("label") == "Find the City Guard"
            and quest_objective(state, "main_quest_lv1").get("target_vnum") == 20354
            for state in (web(), desktop())
        ),
    )
    # Both clients use the production ray-picking and approach path.
    page.mouse.move(*hover_point)
    wait(
        "guard_hover_is_distinct_from_combat",
        lambda: web().get("hover_npc") == spawn_id and not web().get("hover_target"),
    )
    start_position = settled_web_position("browser_position_before_approach_click")
    page.mouse.click(*hover_point)
    wait(
        "browser_approaches_and_receives_private_dialogue",
        lambda: (
            web().get("npc_panel", {}).get("visible")
            and web().get("npc_interaction", {}).get("spawn_id") == spawn_id
        ),
    )
    wait(
        "browser_click_exercises_auto_approach",
        lambda: (
            bool(settled_position(web()))
            and math.dist(settled_position(web()), start_position) > 0.2
        ),
        120,
    )
    # The idle account may be mid refresh; requiring a settled session keeps the
    # negative assertion meaningful instead of reading a drained snapshot.
    wait(
        "idle_account_never_joins_the_browser_conversation",
        lambda: world_session_settled(desktop()) and not desktop().get("npc_interaction"),
    )
    assert not web().get("combat_target"), "NPC became a combat target"
    wait(
        "browser_guard_click_plays_both_scripted_quest_lines",
        lambda: (
            "You must be new in town!" in web().get("npc_panel", {}).get("body", "")
            and "Now go and learn some basics" in web().get("npc_panel", {}).get("body", "")
        ),
    )
    wait(
        "browser_quest_hands_in_origin_and_opens_guardian_chain",
        lambda: (
            quest_state(web(), "main_quest_lv1").get("state") == "__COMPLETE__"
            and quest_state(web(), "find_squareguard").get("state") == "find"
        ),
    )
    assert tracked_letter(web(), "main_quest_lv1") == "", "Completed quest kept its letter"
    assert tracked_letter(web(), "find_squareguard") == "Guardian:"
    assert quest_objective(web(), "find_squareguard").get("target_vnum") == 11000
    # The idle account must keep its own origin quest while the browser account
    # hands that same quest in. The comparison excludes `sequence` because the
    # scheduled session refresh re-fires the quest login triggers and advances
    # it legitimately; a leak overwrites the visible state, the tracked letter
    # and the objective counters, which are all compared exactly. The positive
    # expectations restate the invariant the leak would break, so a drained or
    # half-replayed snapshot can never satisfy the wait vacuously.
    wait(
        "idle_account_keeps_its_own_quest_progress_during_hand_in",
        lambda: (
            own_quest_rows_complete(desktop(), spawn_id)
            and quest_state(desktop(), "main_quest_lv1").get("state") == "gototeacher"
            and tracked_letter(desktop(), "main_quest_lv1") == "Welcome to Metin2"
            and replay_stable_signature(desktop()) == desktop_quests_before
        ),
        120,
    )
    (output / "idle-quests-after.json").write_text(
        json.dumps(
            {
                "full": quest_signature(desktop()),
                "replay_stable": replay_stable_signature(desktop()),
                "browser_hand_in": quest_signature(web()),
            }
        ),
        encoding="utf-8",
    )
    wait(
        "idle_account_still_renders_the_guard_after_hand_in",
        lambda: world_session_settled(desktop()) and bool(npc(desktop(), spawn_id).get("screen")),
        120,
    )
    point = npc(desktop(), spawn_id)["screen"]
    native_command("pointer_click", x=point[0], y=point[1])
    wait(
        "native_click_opens_independent_dialogue",
        lambda: desktop().get("npc_panel", {}).get("visible"),
    )
    assert web().get("npc_interaction", {}).get("session_id") != desktop().get(
        "npc_interaction", {}
    ).get("session_id"), "Both clients shared one dialogue session"
    page.screenshot(path=str(output / "npc-dialogue-browser.png"))
    native_command("capture")
    wait("native_dialogue_capture_saved", lambda: (output / "desktop.png").is_file())
    (output / "desktop.png").replace(output / "npc-dialogue-native.png")
    close_center = settled_web_field(
        "browser_dialogue_close_button_available",
        lambda snapshot: snapshot.get("npc_panel", {}).get("close_center"),
    )
    page.mouse.click(*close_center)
    wait(
        "browser_close_button_closes_exact_session",
        lambda: (
            world_session_settled(web())
            and not web().get("npc_interaction")
            and not web().get("npc_panel", {}).get("visible")
        ),
    )
    wait(
        "native_dialogue_close_button_available",
        lambda: bool(desktop().get("npc_panel", {}).get("close_center")),
    )
    point = desktop()["npc_panel"]["close_center"]
    native_command("pointer_click", x=point[0], y=point[1])
    wait(
        "native_close_button_closes_exact_session",
        lambda: (
            not desktop().get("npc_interaction")
            and not desktop().get("npc_panel", {}).get("visible")
        ),
    )
    reopen_guard_dialogue("browser_can_reopen_after_close", "browser_guard_renders_after_close")
    page.keyboard.press("Escape")
    wait(
        "escape_closes_conversation",
        lambda: not web().get("npc_panel", {}).get("visible"),
    )
    reopen_guard_dialogue(
        "browser_reopens_before_movement", "browser_guard_renders_before_movement"
    )
    position = settled_web_position("browser_position_before_wasd")
    page.keyboard.down("KeyD")
    try:
        wait(
            "WASD_after_dialogue_moves_and_closes_session",
            lambda: (
                not web().get("npc_interaction")
                and len(web().get("server_position", [])) == 3
                and math.dist(web()["server_position"], position) > 0.5
            ),
        )
    finally:
        page.keyboard.up("KeyD")
    web_command("stop")
    # Five of the six remaining Yongan NPCs are authored as boxes rather than
    # points, so `interact_npc` has to resolve them through the live `npc_spawn`
    # row instead of the static placement table. Before that wiring the click
    # came back with "That NPC is not here right now." and no session, which is
    # exactly what this walk and click prove is fixed. The route returns to the
    # guard corridor because the caller's later re-entry check expects the guard
    # to be inside the pinned presentation range.
    for target in route.get("dialogue_targets", []):
        key = target["key"]
        spawn = target["spawn_id"]
        regroup = target.get("regroup")
        if regroup:
            web_command("target", x=regroup[0], z=regroup[1])
            native_command("target", x=regroup[0], z=regroup[1])
            wait(
                f"both_clients_leave_the_guard_for_area_npc_{key}",
                lambda regroup=regroup: arrived(web(), regroup) and arrived(desktop(), regroup),
                30,
            )
        for index, point in enumerate(list(target["waypoints"]) + [target["approach"]]):
            web_command("target", x=point[0], z=point[1])
            native_command("target", x=point[0], z=point[1])
            wait(
                f"both_clients_walk_area_npc_route_{key}_{index + 1}",
                lambda point=point: arrived(web(), point) and arrived(desktop(), point),
                30,
            )
        web_command("stop")
        native_command("stop")
        wait(
            f"area_npc_{key}_renders_from_its_authored_bounds_in_both_exported_cameras",
            lambda spawn=spawn, target=target: all(
                npc(state, spawn).get("in_view")
                and npc(state, spawn).get("playing")
                and npc(state, spawn).get("name") == target["name"]
                for state in (web(), desktop())
            ),
            120,
        )
        if target.get("bounds_cm"):
            wait(
                f"area_npc_{key}_live_row_stays_inside_its_authored_bounds_in_both_exports",
                lambda target=target: area_population_matches(web(), desktop(), [target]),
            )
        point = settled_web_field(
            f"browser_area_npc_{key}_renders_before_click",
            lambda snapshot, spawn=spawn: npc(snapshot, spawn).get("screen") or [],
        )
        page.mouse.move(*point)
        wait(
            f"area_npc_{key}_hover_is_distinct_from_combat",
            lambda spawn=spawn: web().get("hover_npc") == spawn and not web().get("hover_target"),
        )
        page.mouse.click(*point)
        wait(
            f"browser_opens_area_npc_{key}_dialogue_without_a_static_definition",
            lambda spawn=spawn, target=target: (
                web().get("npc_panel", {}).get("visible")
                and web().get("npc_interaction", {}).get("spawn_id") == spawn
                and target["body_contains"] in web().get("npc_panel", {}).get("body", "")
            ),
        )
        if target.get("title"):
            assert web().get("npc_panel", {}).get("title") == target["title"], (
                "Area NPC dialogue lost its original title"
            )
        wait(
            f"idle_account_never_joins_area_npc_{key}_conversation",
            lambda: world_session_settled(desktop()) and not desktop().get("npc_interaction"),
        )
        page.screenshot(path=str(output / f"area-npc-{key}-browser.png"))
        close_center = settled_web_field(
            f"browser_area_npc_{key}_close_button_available",
            lambda snapshot: snapshot.get("npc_panel", {}).get("close_center"),
        )
        page.mouse.click(*close_center)
        wait(
            f"browser_closes_area_npc_{key}_dialogue",
            lambda: (
                world_session_settled(web())
                and not web().get("npc_interaction")
                and not web().get("npc_panel", {}).get("visible")
            ),
        )
        for index, point in enumerate(target.get("return_waypoints", [])):
            web_command("target", x=point[0], z=point[1])
            native_command("target", x=point[0], z=point[1])
            wait(
                f"both_clients_return_from_area_npc_{key}_{index + 1}",
                lambda point=point: arrived(web(), point) and arrived(desktop(), point),
                30,
            )
        web_command("stop")
        native_command("stop")
    if population:
        wait(
            "town_population_preserved_after_guard_route_and_dialogue",
            lambda: all(
                pinned_entry_presentation_matches(state, population, areas)
                for state in (web(), desktop())
            ),
        )
    return before
