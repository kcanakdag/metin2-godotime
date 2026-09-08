"""Exported-client checks for the server-timed Sword+0 combo prefix."""

from __future__ import annotations

import math
import time

from browser_snapshot import POSITION_VALID, subscribed_player_position

DOG_MAX_HEALTH = 100
DOG_RESPAWN_TIMEOUT_SECONDS = 16
DOG_HOME = [675.0, 575.0]
WEB_SAFE_POSITION = [657.0, 575.0]
NATIVE_SAFE_POSITION = [650.0, 575.0]
YONGAN_WALL_ROUTE = [[639.75, 549.5], [640.75, 549.5]]
YONGAN_WALL_HEIGHT_M = 198.625
COMBO_1 = "actor.player.warrior-male.onehand.combo_1"
COMBO_2 = "actor.player.warrior-male.onehand.combo_2"
COMBO_3 = "actor.player.warrior-male.onehand.combo_3"
COMBO_1_PRE_US = 167_094
COMBO_1_DIRECT_US = 533_333
COMBO_1_DURATION_US = 1_000_000
COMBO_2_PRE_US = 100_513
COMBO_2_DIRECT_US = 543_248
COMBO_2_DURATION_US = 933_333
COMBO_3_DURATION_US = 1_066_667
ROOT_ENDPOINTS_M = {
    COMBO_1: 1.317569580078125,
    COMBO_2: 0.852515640258789,
    COMBO_3: 1.4301394653320312,
}
ROOT_PUBLIC_TOLERANCE_M = 0.01
ROOT_RENDER_TOLERANCE_M = 0.05
PLAYER_ATTACK_RANGE_M = 2.7
FOLLOWUP_AFTER_FIRST_ACK_SECONDS = 0.2
FOLLOWUP_AFTER_STEP_2_OBSERVATION_SECONDS = 0.16
TIMING_POLL_SECONDS = 0.01


def _monster(snapshot: dict) -> dict:
    rows = [row for row in snapshot.get("monsters", []) if row.get("definition_vnum") == 101]
    assert isinstance(rows, list) and len(rows) == 1, (
        "Combo export QA requires the normal one-Wild-Dog Yongan fixture"
    )
    row = rows[0]
    assert isinstance(row, dict)
    assert row.get("definition_vnum") == 101 and row.get("name") == "Wild Dog"
    return row


def _player(snapshot: dict, identity: str) -> dict:
    return next(
        (row for row in snapshot.get("player_rows", []) if row.get("identity") == identity),
        {},
    )


def _actor(snapshot: dict, identity: str) -> dict:
    return next(
        (row for row in snapshot.get("actor_presentations", []) if row.get("identity") == identity),
        {},
    )


def _monster_presentation(snapshot: dict, target_id: int) -> dict:
    return next(
        (
            row
            for row in snapshot.get("monster_presentations", [])
            if int(row.get("row_id", 0)) == target_id
        ),
        {},
    )


def _intent_matches(value: dict, target_id: int, life: int) -> bool:
    return (
        isinstance(value, dict)
        and int(value.get("target_id", 0)) == target_id
        and int(value.get("target_life_sequence", -1)) == life
    )


def _pick(snapshot: dict, target_id: int, life: int) -> list[float] | None:
    value = _monster_presentation(snapshot, target_id).get("pick", {})
    point = value.get("screen", []) if isinstance(value, dict) else []
    if (
        not isinstance(value, dict)
        or value.get("available") is not True
        or not _intent_matches(value, target_id, life)
        or not isinstance(point, list)
        or len(point) != 2
        or not all(isinstance(number, (int, float)) and math.isfinite(number) for number in point)
    ):
        return None
    return [float(point[0]), float(point[1])]


def _authoritative_xz(snapshot: dict, identity: str) -> list[float] | None:
    status, position = subscribed_player_position(snapshot, identity)
    if status != POSITION_VALID or position is None:
        return None
    return [float(position[0]), float(position[2])]


def _rendered_xz(snapshot: dict, field: str, key: str, value) -> list[float] | None:
    row = next(
        (
            candidate
            for candidate in snapshot.get(field, [])
            if isinstance(candidate, dict) and candidate.get(key) == value
        ),
        {},
    )
    position = row.get("position", [])
    if (
        not isinstance(position, list)
        or len(position) != 3
        or not all(
            isinstance(number, (int, float)) and math.isfinite(number) for number in position
        )
    ):
        return None
    return [float(position[0]), float(position[2])]


def _sword(snapshot: dict) -> dict:
    return next(row for row in snapshot.get("inventory", []) if int(row.get("vnum", 0)) == 10)


def _last_attack_ack(snapshot: dict) -> dict:
    rows = snapshot.get("perform_attack_acks", [])
    return rows[-1] if isinstance(rows, list) and rows else {}


def _finite_xyz(value) -> list[float] | None:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or not all(isinstance(number, (int, float)) and math.isfinite(number) for number in value)
    ):
        return None
    return [float(value[0]), float(value[1]), float(value[2])]


def _public_xyz(value: dict) -> list[float] | None:
    if not isinstance(value, dict):
        return None
    coordinates = [value.get(field) for field in ("x", "y", "z")]
    return _finite_xyz(coordinates)


def _action_history(snapshot: dict, identity: str, action_id: str, sequence: int) -> list[dict]:
    history = snapshot.get("public_action_history", [])
    if not isinstance(history, list):
        return []
    result: list[dict] = []
    for entry in history:
        if not isinstance(entry, dict) or entry.get("identity") != identity:
            continue
        action = entry.get("public_action", {})
        if (
            not isinstance(action, dict)
            or action.get("attack_action_id") != action_id
            or int(action.get("attack_sequence", -1)) != sequence
        ):
            continue
        public_position = _public_xyz(action)
        rendered_position = _finite_xyz(entry.get("rendered_position"))
        presentation = entry.get("presentation", {})
        if not isinstance(presentation, dict):
            presentation = {}
        server_position = _finite_xyz(presentation.get("server_position"))
        presentation_local = _finite_xyz(presentation.get("presentation_local_position"))
        model_local = _finite_xyz(presentation.get("model_local_position"))
        if public_position is None:
            continue
        entry = entry.copy()
        entry["render_projection_valid"] = all(
            value is not None
            for value in (rendered_position, server_position, presentation_local, model_local)
        )
        result.append(entry)
    return result


def _monster_health_history(snapshot: dict, target_id: int, life: int) -> list[int]:
    history = snapshot.get("monster_health_history", [])
    if not isinstance(history, list):
        return []
    result: list[int] = []
    for entry in history:
        if (
            not isinstance(entry, dict)
            or int(entry.get("id", 0)) != target_id
            or int(entry.get("life_sequence", -1)) != life
            or not isinstance(entry.get("health"), int)
        ):
            continue
        health = int(entry["health"])
        # A reconnect can subscribe the same unchanged public row again. Retain
        # the ordered health transitions without treating that resubscribe as a hit.
        if not result or result[-1] != health:
            result.append(health)
    return result


def _forward_xz(heading: float) -> list[float]:
    assert math.isfinite(heading)
    return [-math.sin(heading), -math.cos(heading)]


def _projected_distance(
    origin: list[float], point: list[float], heading: float
) -> tuple[float, float]:
    forward = _forward_xz(heading)
    delta = [point[0] - origin[0], point[1] - origin[1]]
    along = delta[0] * forward[0] + delta[1] * forward[1]
    cross = abs(delta[0] * forward[1] - delta[1] * forward[0])
    return along, cross


def _action_summary(snapshot: dict, identity: str) -> dict:
    row = _player(snapshot, identity)
    actor = _actor(snapshot, identity)
    monster_rows = snapshot.get("monsters", [])
    monster = (
        monster_rows[0]
        if isinstance(monster_rows, list)
        and len(monster_rows) == 1
        and isinstance(monster_rows[0], dict)
        else {}
    )
    return {
        "connection_state": snapshot.get("connection_state"),
        "identity": snapshot.get("identity"),
        "player": {
            key: row.get(key)
            for key in (
                "activity",
                "attack_action_id",
                "attack_sequence",
                "action_started_at_us",
                "action_ends_at_us",
                "x",
                "y",
                "z",
                "heading",
            )
        },
        "presentation": {
            key: actor.get(key)
            for key in (
                "action_id",
                "attack_sequence",
                "sequence",
                "animation_position",
                "server_position",
                "presentation_local_position",
                "model_local_position",
            )
        },
        "monster": {
            key: monster.get(key)
            for key in ("id", "life_sequence", "health", "max_health", "activity", "x", "z")
        },
        "monster_row_count": len(monster_rows) if isinstance(monster_rows, list) else None,
        "combat_target": snapshot.get("combat_target", {}),
        "last_attack_ack": _last_attack_ack(snapshot),
    }


def exercise_combo(
    page,
    web,
    desktop,
    web_command,
    native_command,
    wait,
    web_id: str,
    native_id: str,
    output,
    diagnostics: dict,
) -> dict:
    """Exercise accepted combo links and movement/target cancellations."""

    started = time.monotonic()
    phase = "initial"
    trace: list[dict] = []
    timing_attempts: list[dict] = []
    evidence: dict[str, object] = {}
    diagnostics.clear()
    diagnostics.update(
        {"phase": phase, "trace": trace, "timing_attempts": timing_attempts, "evidence": evidence}
    )

    read_web, read_desktop = web, desktop

    def observe(side: str, snapshot: dict) -> dict:
        trace.append(
            {
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "phase": phase,
                "side": side,
                **_action_summary(snapshot, web_id if side == "web" else native_id),
            }
        )
        del trace[:-96]
        return snapshot

    def web() -> dict:
        return observe("web", read_web())

    def desktop() -> dict:
        return observe("native", read_desktop())

    def set_phase(value: str) -> None:
        nonlocal phase
        phase = value
        diagnostics["phase"] = value
        diagnostics["elapsed_seconds"] = round(time.monotonic() - started, 3)

    def cell_point(snapshot: dict, cell: int) -> list[float]:
        origin = snapshot["ui"]["grid_origin"]
        return [origin[0] + (cell % 5) * 32 + 16, origin[1] + (cell % 45 // 5) * 32 + 16]

    def browser_drag(start: list[float], end: list[float]) -> None:
        page.mouse.move(*start)
        page.mouse.down()
        page.mouse.move(start[0] + 12, start[1] + 5, steps=5)
        page.mouse.move(*end, steps=20)
        page.mouse.up()

    def equipment_ready(snapshot: dict, owner: str, equipped: bool, cell: int) -> bool:
        sword = _sword(snapshot)
        local = _actor(snapshot, owner)
        peer_snapshot = desktop() if owner == web_id else web()
        peer = _actor(peer_snapshot, owner)
        weapon = 10 if equipped else 0
        return (
            bool(sword.get("equipped")) is equipped
            and (equipped or int(sword.get("cell", -1)) == cell)
            and int(local.get("weapon_vnum", -1)) == weapon
            and bool(local.get("equipment_attached")) is equipped
            and int(peer.get("weapon_vnum", -1)) == weapon
            and bool(peer.get("equipment_attached")) is equipped
        )

    original_swords = {
        "web": _sword(web()).copy(),
        "native": _sword(desktop()).copy(),
    }
    original_inventory = {
        "web": sorted(web().get("inventory", []), key=lambda row: int(row["id"])),
        "native": sorted(desktop().get("inventory", []), key=lambda row: int(row["id"])),
    }
    assert not original_swords["web"].get("equipped")
    assert not original_swords["native"].get("equipped")
    assert int(original_swords["native"].get("cell", -1)) == 0, (
        "The fixed native right-click unequip restores the untouched starter Sword+0 cell"
    )

    def set_inventory_open(side: str, visible: bool) -> None:
        read = web if side == "web" else desktop
        if bool(read().get("ui", {}).get("visible")) == visible:
            return
        if side == "web":
            page.locator("canvas").focus()
            page.keyboard.press("i")
        else:
            native_command("inventory")
        wait(
            f"combo_{side}_inventory_{'opens' if visible else 'closes'}",
            lambda: bool(read()["ui"]["visible"]) is visible,
        )

    def click_inventory(side: str, point: list[float], right: bool = False) -> None:
        if side == "web":
            page.mouse.click(*point, button="right" if right else "left")
        else:
            native_command(
                "pointer_right_click" if right else "pointer_click", x=point[0], y=point[1]
            )

    def equip(side: str, owner: str) -> None:
        read = web if side == "web" else desktop
        original = original_swords[side]
        cell = int(original["cell"])
        set_inventory_open(side, True)
        state = read()
        click_inventory(side, list(state["ui"]["tab_centers"][cell // 45]))
        wait(f"combo_{side}_shows_sword_page", lambda: int(read()["ui"]["page"]) == cell // 45)
        click_inventory(side, cell_point(read(), cell), True)
        wait(
            f"combo_{side}_Sword0_projects_to_both_clients",
            lambda: equipment_ready(read(), owner, True, cell),
        )
        set_inventory_open(side, False)

    def unequip(side: str, owner: str) -> None:
        read = web if side == "web" else desktop
        original = original_swords[side]
        cell = int(original["cell"])
        incoming_page = int(original.get("ui_page", cell // 45))
        set_inventory_open(side, True)
        state = read()
        click_inventory(side, list(state["ui"]["tab_centers"][cell // 45]))
        wait(f"combo_{side}_restores_sword_page", lambda: int(read()["ui"]["page"]) == cell // 45)
        state = read()
        equipment = state["ui"]["equipment_origin"]
        if side == "web":
            browser_drag([equipment[0] + 16, equipment[1] + 16], cell_point(state, cell))
        else:
            click_inventory(side, [equipment[0] + 16, equipment[1] + 16], True)
        wait(
            f"combo_{side}_restores_original_sword_cell_for_both_clients",
            lambda: equipment_ready(read(), owner, False, cell),
        )
        state = read()
        click_inventory(side, list(state["ui"]["tab_centers"][incoming_page]))
        wait(
            f"combo_{side}_restores_incoming_inventory_page",
            lambda: int(read()["ui"]["page"]) == incoming_page,
        )
        set_inventory_open(side, False)

    # UI page is local preference rather than an inventory row; retain it separately.
    original_swords["web"]["ui_page"] = int(web()["ui"]["page"])
    original_swords["native"]["ui_page"] = int(desktop()["ui"]["page"])

    def move_near(side: str, owner: str) -> None:
        read = web if side == "web" else desktop
        command = web_command if side == "web" else native_command
        approach: dict = {
            "home_settle_samples": [],
            "movement_samples": [],
            "waypoints": [],
        }
        approaches = evidence.setdefault("approaches", [])
        assert isinstance(approaches, list)
        approaches.append(approach)
        approach["side"] = side
        approach["index"] = len(approaches)
        initial = read()
        dog = _monster(initial)
        player = _authoritative_xz(initial, owner)
        already_near = (
            player is not None and math.dist(player, [float(dog["x"]), float(dog["z"])]) < 2.6
        )
        approach["already_in_reach"] = already_near
        if not already_near:
            stable_since: float | None = None
            stable_dog: list[float] | None = None

            def dog_is_stable_at_home() -> bool:
                nonlocal stable_since, stable_dog
                state = read()
                current = _monster(state)
                position = [float(current["x"]), float(current["z"])]
                rendered = _rendered_xz(state, "rendered_monsters", "row_id", int(current["id"]))
                valid = (
                    int(current["health"]) > 0
                    and int(current["activity"]) != 1
                    and math.dist(position, DOG_HOME) <= 0.25
                    and rendered is not None
                    and math.dist(position, rendered) <= 0.05
                )
                sample = {
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "valid": valid,
                    "authoritative_monster_xz": position,
                    "rendered_monster_xz": rendered,
                    "activity": int(current["activity"]),
                }
                approach["home_settle_samples"].append(sample)
                del approach["home_settle_samples"][:-24]
                now = time.monotonic()
                if not valid or stable_dog is None or math.dist(position, stable_dog) > 0.05:
                    stable_since = now if valid else None
                    stable_dog = position if valid else None
                    approach["stable_home_seconds"] = 0.0
                    return False
                assert stable_since is not None
                approach["stable_home_seconds"] = round(now - stable_since, 3)
                return now - stable_since >= 0.5

            wait(f"combo_{side}_waits_for_stable_Wild_Dog_home", dog_is_stable_at_home, 15)

            state = read()
            dog = _monster(state)
            waypoint = [float(dog["x"]), float(dog["z"])]
            approach["waypoints"].append(
                {
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "world_xz": waypoint,
                    "dog_activity": int(dog["activity"]),
                }
            )
            command("target", x=waypoint[0], z=waypoint[1])

        def reached() -> bool:
            state = read()
            current = _monster(state)
            point = _authoritative_xz(state, owner)
            dog_position = [float(current["x"]), float(current["z"])]
            approach["movement_samples"].append(
                {
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "authoritative_player_xz": point,
                    "authoritative_monster_xz": dog_position,
                    "distance_meters": math.dist(point, dog_position)
                    if point is not None
                    else None,
                    "monster_activity": int(current["activity"]),
                }
            )
            del approach["movement_samples"][:-24]
            return (
                point is not None
                and int(current.get("health", 0)) > 0
                and math.dist(point, dog_position) < 2.6
            )

        wait(f"combo_{side}_reaches_live_Wild_Dog", reached, 15)
        command("stop")
        wait(f"combo_{side}_stops_in_attack_reach", lambda: int(read().get("activity", -1)) == 0)

    def move_safe(side: str, owner: str) -> None:
        read = web if side == "web" else desktop
        command = web_command if side == "web" else native_command
        expected = WEB_SAFE_POSITION if side == "web" else NATIVE_SAFE_POSITION
        command("target", x=expected[0], z=expected[1])
        wait(
            f"combo_{side}_returns_outside_dog_chase",
            lambda: (
                (point := _authoritative_xz(read(), owner)) is not None
                and math.dist(point, expected) < 0.5
            ),
            15,
        )
        command("stop")
        wait(f"combo_{side}_safe_position_is_stopped", lambda: int(read().get("activity", -1)) == 0)

    def settled_pick(side: str, owner: str, target_id: int, life: int) -> tuple[dict, list[float]]:
        read = web if side == "web" else desktop
        stable_since: float | None = None
        stable_point: list[float] | None = None
        settled: dict = {}

        def ready() -> bool:
            nonlocal stable_since, stable_point, settled
            state = read()
            dog = _monster(state)
            point = _pick(state, target_id, life)
            authoritative = _authoritative_xz(state, owner)
            rendered = _rendered_xz(state, "rendered_actors", "identity", owner)
            dog_xz = [float(dog["x"]), float(dog["z"])]
            rendered_dog = _rendered_xz(state, "rendered_monsters", "row_id", target_id)
            valid = (
                int(dog.get("life_sequence", -1)) == life
                and int(dog.get("health", 0)) > 0
                and int(dog.get("activity", -1)) != 1
                and int(_player(state, owner).get("activity", -1)) == 0
                and point is not None
                and authoritative is not None
                and rendered is not None
                and rendered_dog is not None
                and math.dist(authoritative, rendered) <= 0.05
                and math.dist(dog_xz, rendered_dog) <= 0.05
            )
            if not valid:
                stable_since = None
                stable_point = None
                return False
            now = time.monotonic()
            if stable_since is None or stable_point is None or math.dist(point, stable_point) > 1.0:
                stable_since = now
                stable_point = point
                return False
            if now - stable_since < 0.5:
                return False
            settled = state
            return True

        wait(f"combo_{side}_pick_projection_settles_before_input", ready, 15)
        point = _pick(settled, target_id, life)
        assert point is not None
        return settled, point

    def select(side: str, owner: str, target_id: int, life: int) -> list[float]:
        state, point = settled_pick(side, owner, target_id, life)
        ack_sequence = int(last_target_ack(side).get("sequence", 0))
        if side == "web":
            page.mouse.click(*point)
        else:
            native_command("pointer_click", x=point[0], y=point[1])
        read = web if side == "web" else desktop
        wait(
            f"combo_{side}_canvas_selects_exact_life",
            lambda: _intent_matches(read().get("combat_target", {}), target_id, life),
        )
        selection_ack = wait_for_target_ack(side, ack_sequence, target_id, life)
        evidence[f"{side}_selection"] = {
            "before": _action_summary(state, owner),
            "ack": selection_ack,
        }
        return point

    def press_space(side: str, ensure_focus: bool = True) -> None:
        if side == "web":
            if ensure_focus:
                page.locator("canvas").focus()
            page.keyboard.press("Space")
        else:
            native_command("space")

    def last_attack_ack(side: str) -> dict:
        if side == "web":
            rows = page.evaluate("() => JSON.parse(window.mt2AttackAcks || '[]')")
            assert isinstance(rows, list)
            return rows[-1] if rows and isinstance(rows[-1], dict) else {}
        return _last_attack_ack(desktop())

    def last_target_ack(side: str) -> dict:
        if side == "web":
            rows = page.evaluate("() => JSON.parse(window.mt2SelectTargetAcks || '[]')")
            assert isinstance(rows, list)
            return rows[-1] if rows and isinstance(rows[-1], dict) else {}
        rows = desktop().get("select_combat_target_acks", [])
        return rows[-1] if isinstance(rows, list) and rows else {}

    def probe_errors(side: str) -> list[str]:
        if side == "web":
            values = page.evaluate("() => JSON.parse(window.mt2ProbeErrors || '[]')")
        else:
            values = desktop().get("errors", [])
        return [str(value) for value in values] if isinstance(values, list) else []

    def own_action_transition(side: str, owner: str) -> dict:
        if side == "web":
            value = page.evaluate("() => JSON.parse(window.mt2OwnPublicAction || '{}')")
            return value if isinstance(value, dict) else {}
        return _player(desktop(), owner).copy()

    def web_player_projection(owner: str) -> dict:
        value = page.evaluate(
            """
            owner => {
                const snapshot = JSON.parse(window.mt2Snapshot || '{}');
                const rows = Array.isArray(snapshot.player_rows) ? snapshot.player_rows : [];
                const player = rows.find(row => row && row.identity === owner) || {};
                return {player, ground_pick: snapshot.ground_pick || {}};
            }
            """,
            owner,
        )
        assert isinstance(value, dict) and isinstance(value.get("player"), dict)
        return value

    def web_live_pick_projection(owner: str, target_id: int) -> dict:
        value = page.evaluate(
            """
            ({ owner, targetId }) => {
                const snapshot = JSON.parse(window.mt2Snapshot || '{}');
                const rows = (name, key, expected) => {
                    const values = Array.isArray(snapshot[name]) ? snapshot[name] : [];
                    return values.filter(row => row && row[key] === expected);
                };
                return {
                    connection_state: snapshot.connection_state,
                    identity: snapshot.identity,
                    combat_target: snapshot.combat_target || {},
                    monsters: rows('monsters', 'id', targetId),
                    monster_presentations: rows('monster_presentations', 'row_id', targetId),
                    player_rows: rows('player_rows', 'identity', owner),
                    actor_presentations: rows('actor_presentations', 'identity', owner),
                    rendered_actors: rows('rendered_actors', 'identity', owner),
                    rendered_monsters: rows('rendered_monsters', 'row_id', targetId),
                };
            }
            """,
            {"owner": owner, "targetId": target_id},
        )
        assert isinstance(value, dict)
        return value

    def wait_for_ack(side: str, after: int, succeeded: bool) -> dict:
        found: dict = {}

        def ready() -> bool:
            nonlocal found
            ack = last_attack_ack(side)
            sequence = int(ack.get("sequence", 0))
            if sequence <= after:
                return False
            if sequence != after + 1:
                evidence.setdefault("unexpected_attack_acks", []).append(
                    {
                        "side": side,
                        "after_sequence": after,
                        "expected_succeeded": succeeded,
                        "actual": ack.copy(),
                        "errors": probe_errors(side),
                    }
                )
                raise AssertionError("Attack ACK sequence skipped the expected reducer completion")
            found = ack.copy()
            if bool(ack.get("succeeded")) is not succeeded:
                evidence.setdefault("unexpected_attack_acks", []).append(
                    {
                        "side": side,
                        "after_sequence": after,
                        "expected_succeeded": succeeded,
                        "actual": found,
                        "errors": probe_errors(side),
                    }
                )
                raise AssertionError("The exact next attack ACK had the wrong outcome")
            return True

        wait(
            f"combo_{side}_perform_attack_ack_{after + 1}_{'succeeds' if succeeded else 'rejects'}",
            ready,
            3,
            TIMING_POLL_SECONDS,
        )
        return found

    def wait_for_target_ack(side: str, after: int, target_id: int, life: int) -> dict:
        found: dict = {}

        def ready() -> bool:
            nonlocal found
            ack = last_target_ack(side)
            sequence = int(ack.get("sequence", 0))
            if sequence <= after:
                return False
            if sequence != after + 1:
                evidence.setdefault("unexpected_target_acks", []).append(
                    {
                        "side": side,
                        "after_sequence": after,
                        "actual": ack.copy(),
                        "errors": probe_errors(side),
                    }
                )
                raise AssertionError("Target ACK sequence skipped the expected reducer completion")
            found = ack.copy()
            if not bool(ack.get("succeeded")):
                evidence.setdefault("unexpected_target_acks", []).append(
                    {
                        "side": side,
                        "after_sequence": after,
                        "actual": found,
                        "errors": probe_errors(side),
                    }
                )
                raise AssertionError("The exact next target renewal ACK was rejected")
            if not _intent_matches(ack.get("combat_target", {}), target_id, life):
                evidence.setdefault("unexpected_target_acks", []).append(
                    {
                        "side": side,
                        "after_sequence": after,
                        "actual": found,
                        "errors": probe_errors(side),
                    }
                )
                raise AssertionError("Accepted target ACK did not retain the selected exact life")
            return True

        wait(
            f"combo_{side}_same_life_target_renewal_is_accepted",
            ready,
            3,
            TIMING_POLL_SECONDS,
        )
        return found

    def current_live_pick(
        side: str, owner: str, target_id: int, life: int
    ) -> tuple[dict, list[float]]:
        state = web_live_pick_projection(owner, target_id) if side == "web" else desktop()
        dog = _monster(state)
        point = _pick(state, target_id, life)
        authoritative = _authoritative_xz(state, owner)
        rendered = _rendered_xz(state, "rendered_actors", "identity", owner)
        rendered_dog = _rendered_xz(state, "rendered_monsters", "row_id", target_id)
        dog_xz = [float(dog["x"]), float(dog["z"])]
        checks = evidence.setdefault("renewal_pick_checks", [])
        assert isinstance(checks, list)
        checks.append(
            {
                "side": side,
                "action": _action_summary(state, owner),
                "target_id": target_id,
                "target_life_sequence": life,
                "pick": point,
                "authoritative_player_xz": authoritative,
                "rendered_player_xz": rendered,
                "player_interpolation_lag_m": (
                    math.dist(authoritative, rendered)
                    if authoritative is not None and rendered is not None
                    else None
                ),
                "authoritative_monster_xz": dog_xz,
                "rendered_monster_xz": rendered_dog,
                "monster_render_error_m": (
                    math.dist(dog_xz, rendered_dog) if rendered_dog is not None else None
                ),
            }
        )
        del checks[:-8]
        assert (
            int(dog["life_sequence"]) == life
            and int(dog["health"]) > 0
            and point is not None
            and authoritative is not None
            and rendered is not None
            and rendered_dog is not None
            and math.dist(dog_xz, rendered_dog) <= ROOT_RENDER_TOLERANCE_M
        ), "Renewal requires a current exact-life in-viewport pick from the live rendered monster"
        return state, point

    def collect_history_evidence(
        side: str,
        owner: str,
        peer_read,
        action_id: str,
        sequence: int,
        observed: dict,
    ) -> bool:
        read = web if side == "web" else desktop
        for name, reader in (("local", read), ("peer", peer_read)):
            state = reader()
            rows = _action_history(state, owner, action_id, sequence)
            if not rows:
                continue
            value = observed.setdefault(name, {})
            value["public_first"] = rows[0]
            value["public_latest"] = rows[-1]
            value["public_samples"] = rows
            for row in rows:
                presentation = row.get("presentation", {})
                if (
                    isinstance(presentation, dict)
                    and presentation.get("action_id") == action_id
                    and int(presentation.get("attack_sequence", -1)) == sequence
                ):
                    value.setdefault("rendered_action", row)
                    break
        return all(
            name in observed
            and "public_first" in observed[name]
            and "rendered_action" in observed[name]
            for name in ("local", "peer")
        )

    def wait_for_history_evidence(
        label: str,
        side: str,
        owner: str,
        peer_read,
        action_id: str,
        sequence: int,
        observed: dict,
    ) -> dict:
        wait(
            label,
            lambda: collect_history_evidence(side, owner, peer_read, action_id, sequence, observed),
            3,
            TIMING_POLL_SECONDS,
        )
        return observed

    def validate_root_segment(
        label: str,
        action_id: str,
        duration_us: int,
        start_action: dict,
        through_us: int,
        end_action: dict,
    ) -> dict:
        start = _public_xyz(start_action)
        end = _public_xyz(end_action)
        heading = float(start_action.get("heading", math.nan))
        assert start is not None and end is not None and math.isfinite(heading)
        elapsed_us = max(
            0, min(duration_us, through_us - int(start_action["action_started_at_us"]))
        )
        expected = ROOT_ENDPOINTS_M[action_id] * elapsed_us / duration_us
        along, cross = _projected_distance([start[0], start[2]], [end[0], end[2]], heading)
        assert abs(along - expected) <= ROOT_PUBLIC_TOLERANCE_M, (
            f"{label} subscribed endpoint differs from the source-derived root fraction"
        )
        assert cross <= ROOT_PUBLIC_TOLERANCE_M, (
            f"{label} subscribed endpoint drifts across its captured heading"
        )
        return {
            "action_id": action_id,
            "start": start_action,
            "through_us": through_us,
            "end": end_action,
            "elapsed_us": elapsed_us,
            "expected_along_m": expected,
            "observed_along_m": along,
            "observed_cross_m": cross,
            "position_tolerance_m": ROOT_PUBLIC_TOLERANCE_M,
        }

    def validate_action_history(
        label: str,
        action_id: str,
        start_action: dict,
        end_along_m: float,
        observed: dict,
    ) -> dict:
        start = _public_xyz(start_action)
        heading = float(start_action.get("heading", math.nan))
        assert start is not None and math.isfinite(heading)
        summary: dict[str, object] = {}
        for side_name in ("local", "peer"):
            rows = observed[side_name]["public_samples"]
            assert rows
            previous = -ROOT_PUBLIC_TOLERANCE_M
            baseline_presentation: list[float] | None = None
            baseline_model: list[float] | None = None
            valid_render_projections = 0
            samples: list[dict] = []
            for entry in rows:
                action = entry["public_action"]
                point = _public_xyz(action)
                assert point is not None
                assert float(action.get("heading", math.nan)) == heading, (
                    f"{label} {side_name} changed heading inside one accepted action"
                )
                along, cross = _projected_distance(
                    [start[0], start[2]], [point[0], point[2]], heading
                )
                assert along + ROOT_PUBLIC_TOLERANCE_M >= previous, (
                    f"{label} {side_name} subscribed root regressed along its heading"
                )
                assert along <= end_along_m + ROOT_PUBLIC_TOLERANCE_M
                assert cross <= ROOT_PUBLIC_TOLERANCE_M
                previous = max(previous, along)
                presentation = entry.get("presentation", {})
                presentation_local = _finite_xyz(
                    presentation.get("presentation_local_position")
                    if isinstance(presentation, dict)
                    else None
                )
                model_local = _finite_xyz(
                    presentation.get("model_local_position")
                    if isinstance(presentation, dict)
                    else None
                )
                rendered_action = (
                    isinstance(presentation, dict)
                    and presentation.get("action_id") == action_id
                    and int(presentation.get("attack_sequence", -1))
                    == int(action.get("attack_sequence", -2))
                )
                if rendered_action and presentation_local is not None and model_local is not None:
                    baseline_presentation = baseline_presentation or presentation_local
                    baseline_model = baseline_model or model_local
                    assert math.dist(presentation_local, baseline_presentation) <= 0.0001
                    assert math.dist(model_local, baseline_model) <= 0.0001
                    valid_render_projections += 1
                sample = entry.copy()
                sample["along_m"] = along
                sample["cross_m"] = cross
                samples.append(sample)
            assert valid_render_projections > 0, (
                f"{label} {side_name} has no independent rendered action projection"
            )
            summary[side_name] = {
                "samples": samples,
                "valid_render_projections": valid_render_projections,
                "max_observed_along_m": previous,
            }
        local_first = observed["local"]["public_first"]["public_action"]
        peer_first = observed["peer"]["public_first"]["public_action"]
        for field in (
            "attack_action_id",
            "attack_sequence",
            "action_started_at_us",
            "action_ends_at_us",
            "heading",
        ):
            assert local_first.get(field) == peer_first.get(field), (
                f"{label} public start field {field} differs between subscriptions"
            )
        local_position = _public_xyz(local_first)
        peer_position = _public_xyz(peer_first)
        assert local_position is not None and peer_position is not None
        assert math.dist(local_position, peer_position) <= ROOT_PUBLIC_TOLERANCE_M
        return summary

    def run_three_hit_chain(side: str, owner: str, peer_read) -> dict:
        read = web if side == "web" else desktop
        before_state = read()
        dog = _monster(before_state)
        before_health = int(dog["health"])
        assert before_health == DOG_MAX_HEALTH
        sequence = int(_player(before_state, owner).get("attack_sequence", 0))
        ack_sequence = int(last_attack_ack(side).get("sequence", 0))
        sent_at = time.monotonic()
        press_space(side)
        first_ack = wait_for_ack(side, ack_sequence, True)
        first_ack_observed_at = time.monotonic()
        timing = {
            "side": side,
            "kind": "positive_chain",
            "first_command_elapsed_seconds": round(sent_at - started, 3),
            "first_ack_observed_elapsed_seconds": round(first_ack_observed_at - started, 3),
            "first_ack_observation_after_command_seconds": round(
                first_ack_observed_at - sent_at, 3
            ),
            "first_ack": first_ack,
        }
        timing_attempts.append(timing)
        deadline = first_ack_observed_at + FOLLOWUP_AFTER_FIRST_ACK_SECONDS
        timing["followup_deadline_elapsed_seconds"] = round(deadline - started, 3)
        ack_sequence = int(first_ack["sequence"])
        first_public = first_ack.get("public_action", {})
        assert first_public.get("attack_action_id") == COMBO_1
        assert int(first_public.get("attack_sequence", -1)) == sequence + 1
        time.sleep(max(0.0, deadline - time.monotonic()))
        followup_sent_at = time.monotonic()
        timing["followup_command_elapsed_seconds"] = round(followup_sent_at - started, 3)
        timing["followup_command_after_first_ack_seconds"] = round(
            followup_sent_at - first_ack_observed_at, 3
        )
        timing["followup_command_lateness_seconds"] = round(
            max(0.0, followup_sent_at - deadline), 3
        )
        press_space(side, False)
        queued_ack = wait_for_ack(side, ack_sequence, True)
        queue_ack_observed_at = time.monotonic()
        timing["queue_ack"] = queued_ack
        timing["queue_ack_observed_elapsed_seconds"] = round(queue_ack_observed_at - started, 3)
        timing["queue_ack_observation_after_followup_seconds"] = round(
            queue_ack_observed_at - followup_sent_at, 3
        )
        assert queued_ack.get("public_action", {}).get("attack_action_id") == COMBO_1, (
            "Successful queue ACK must be observed while the public action remains combo_1"
        )
        assert int(queued_ack.get("public_action", {}).get("attack_sequence", -1)) == sequence + 1
        queue_receipt_us = int(queued_ack.get("reducer_timestamp_us", 0))
        first_started_us = int(first_public.get("action_started_at_us", 0))
        assert first_started_us > 0
        queue_elapsed_us = queue_receipt_us - first_started_us
        timing["queue_receipt_after_combo_1_us"] = queue_elapsed_us
        assert COMBO_1_PRE_US < queue_elapsed_us <= COMBO_1_DIRECT_US, (
            "Successful follow-up must be a queued receipt inside the source-defined window"
        )
        target_id = int(dog["id"])
        life = int(dog["life_sequence"])
        target_ack_sequence = (
            int(last_target_ack(side).get("sequence", 0)) if side == "web" else None
        )
        renewal_pick_started_at = time.monotonic()
        renew_state, renew_point = current_live_pick(side, owner, target_id, life)
        renewal_pick_observed_at = time.monotonic()
        timing["renewal_pick_read_seconds"] = round(
            renewal_pick_observed_at - renewal_pick_started_at, 3
        )
        timing["renewal_pick_observed_elapsed_seconds"] = round(
            renewal_pick_observed_at - started, 3
        )
        if side != "web":
            target_rows = renew_state.get("select_combat_target_acks", [])
            target_ack = target_rows[-1] if isinstance(target_rows, list) and target_rows else {}
            target_ack_sequence = int(target_ack.get("sequence", 0))
        assert target_ack_sequence is not None
        renewal_sent_at = time.monotonic()
        if side == "web":
            page.mouse.click(*renew_point)
        else:
            native_command("pointer_click", x=renew_point[0], y=renew_point[1])
        timing["renewal_command_elapsed_seconds"] = round(renewal_sent_at - started, 3)
        renewal_ack = wait_for_target_ack(side, target_ack_sequence, target_id, life)
        renewal_ack_observed_at = time.monotonic()
        timing["renewal_ack"] = renewal_ack
        timing["renewal_ack_observed_elapsed_seconds"] = round(renewal_ack_observed_at - started, 3)
        timing["renewal_ack_observation_after_command_seconds"] = round(
            renewal_ack_observed_at - renewal_sent_at, 3
        )
        renewal_receipt_us = int(renewal_ack.get("reducer_timestamp_us", 0))
        timing["renewal_receipt_after_combo_1_us"] = renewal_receipt_us - first_started_us
        assert renewal_ack.get("public_action", {}).get("attack_action_id") == COMBO_1, (
            "Same-target renewal must be accepted while the queued first step is still public"
        )
        assert int(renewal_ack.get("public_action", {}).get("attack_sequence", -1)) == sequence + 1
        assert queue_receipt_us < renewal_receipt_us
        first = first_public.copy()
        step_2_observation: dict = {}
        second: dict = {}

        def combo_2_is_current() -> bool:
            nonlocal second
            action = own_action_transition(side, owner)
            if (
                int(action.get("activity", -1)) != 2
                or action.get("attack_action_id") != COMBO_2
                or int(action.get("attack_sequence", -1)) != sequence + 2
            ):
                return False
            second = action.copy()
            return True

        wait(
            f"combo_{side}_step2_own_authoritative_transition_is_observed",
            combo_2_is_current,
            3,
            TIMING_POLL_SECONDS,
        )
        second_observed_at = time.monotonic()
        transition_us = int(second["action_started_at_us"]) - int(first["action_started_at_us"])
        assert COMBO_1_DIRECT_US < transition_us < COMBO_1_DURATION_US
        assert renewal_receipt_us < int(second["action_started_at_us"]), (
            "Accepted same-target renewal must precede the queued server transition"
        )
        timing["combo_2_observed_elapsed_seconds"] = round(second_observed_at - started, 3)
        third_deadline = second_observed_at + FOLLOWUP_AFTER_STEP_2_OBSERVATION_SECONDS
        timing["third_followup_deadline_elapsed_seconds"] = round(third_deadline - started, 3)
        timing["third_followup_after_combo_2_observation_seconds"] = (
            FOLLOWUP_AFTER_STEP_2_OBSERVATION_SECONDS
        )
        time.sleep(max(0.0, third_deadline - time.monotonic()))
        third_sent_at = time.monotonic()
        timing["third_followup_command_elapsed_seconds"] = round(third_sent_at - started, 3)
        timing["third_followup_command_after_combo_2_observation_seconds"] = round(
            third_sent_at - second_observed_at, 3
        )
        timing["third_followup_command_lateness_seconds"] = round(
            max(0.0, third_sent_at - third_deadline), 3
        )
        press_space(side, False)
        third_ack = wait_for_ack(side, int(queued_ack["sequence"]), True)
        third_ack_observed_at = time.monotonic()
        timing["third_queue_ack"] = third_ack
        timing["third_queue_ack_observed_elapsed_seconds"] = round(
            third_ack_observed_at - started, 3
        )
        third_public = third_ack.get("public_action", {})
        assert third_public.get("attack_action_id") == COMBO_2, (
            "Successful third-step queue ACK must retain subscribed combo_2"
        )
        assert int(third_public.get("attack_sequence", -1)) == sequence + 2
        third_receipt_us = int(third_ack.get("reducer_timestamp_us", 0))
        second_started_us = int(second["action_started_at_us"])
        third_queue_elapsed_us = third_receipt_us - second_started_us
        timing["queue_receipt_after_combo_2_us"] = third_queue_elapsed_us
        assert COMBO_2_PRE_US < third_queue_elapsed_us <= COMBO_2_DIRECT_US, (
            "Successful third-step follow-up must be queued inside combo_2's source window"
        )

        target_ack_sequence = (
            int(last_target_ack(side).get("sequence", 0)) if side == "web" else None
        )
        second_renewal_pick_started_at = time.monotonic()
        renew_state, renew_point = current_live_pick(side, owner, target_id, life)
        second_renewal_pick_observed_at = time.monotonic()
        timing["combo_2_renewal_pick_read_seconds"] = round(
            second_renewal_pick_observed_at - second_renewal_pick_started_at, 3
        )
        timing["combo_2_renewal_pick_observed_elapsed_seconds"] = round(
            second_renewal_pick_observed_at - started, 3
        )
        if side != "web":
            target_rows = renew_state.get("select_combat_target_acks", [])
            target_ack = target_rows[-1] if isinstance(target_rows, list) and target_rows else {}
            target_ack_sequence = int(target_ack.get("sequence", 0))
        assert target_ack_sequence is not None
        second_renewal_sent_at = time.monotonic()
        if side == "web":
            page.mouse.click(*renew_point)
        else:
            native_command("pointer_click", x=renew_point[0], y=renew_point[1])
        timing["combo_2_renewal_command_elapsed_seconds"] = round(
            second_renewal_sent_at - started, 3
        )
        second_renewal_ack = wait_for_target_ack(side, target_ack_sequence, target_id, life)
        second_renewal_ack_observed_at = time.monotonic()
        second_renewal_receipt_us = int(second_renewal_ack.get("reducer_timestamp_us", 0))
        timing["combo_2_renewal_ack"] = second_renewal_ack
        timing["combo_2_renewal_ack_observed_elapsed_seconds"] = round(
            second_renewal_ack_observed_at - started, 3
        )
        timing["combo_2_renewal_ack_observation_after_command_seconds"] = round(
            second_renewal_ack_observed_at - second_renewal_sent_at, 3
        )
        timing["combo_2_renewal_receipt_after_combo_2_us"] = (
            second_renewal_receipt_us - second_started_us
        )
        assert third_receipt_us < second_renewal_receipt_us
        assert second_renewal_ack.get("public_action", {}).get("attack_action_id") == COMBO_2
        assert int(second_renewal_ack.get("public_action", {}).get("attack_sequence", -1)) == (
            sequence + 2
        )

        third: dict = {}

        def combo_3_is_current() -> bool:
            nonlocal third
            action = own_action_transition(side, owner)
            if (
                int(action.get("activity", -1)) != 2
                or action.get("attack_action_id") != COMBO_3
                or int(action.get("attack_sequence", -1)) != sequence + 3
            ):
                return False
            third = action.copy()
            return True

        wait(
            f"combo_{side}_step3_own_authoritative_transition_is_observed",
            combo_3_is_current,
            3,
            TIMING_POLL_SECONDS,
        )
        timing["combo_3_observed_elapsed_seconds"] = round(time.monotonic() - started, 3)
        transition_2_us = int(third["action_started_at_us"]) - int(second["action_started_at_us"])
        assert COMBO_2_DIRECT_US < transition_2_us < COMBO_2_DURATION_US
        assert second_renewal_receipt_us < int(third["action_started_at_us"]), (
            "Accepted combo_2 same-target renewal must precede the queued combo_3 transition"
        )

        death_states: dict[str, dict] = {}

        def lethal_hit_is_current_on_both_clients() -> bool:
            local_state = read()
            peer_state = peer_read()
            local_player = _player(local_state, owner)
            peer_player = _player(peer_state, owner)
            if not (
                int(_monster(local_state)["life_sequence"]) == life
                and int(_monster(peer_state)["life_sequence"]) == life
                and int(_monster(local_state)["health"]) == 0
                and int(_monster(peer_state)["health"]) == 0
                and not local_state.get("combat_target")
                and int(local_player.get("activity", -1)) == 2
                and local_player.get("attack_action_id") == COMBO_3
                and int(local_player.get("attack_sequence", -1)) == sequence + 3
                and int(peer_player.get("activity", -1)) == 2
                and peer_player.get("attack_action_id") == COMBO_3
                and int(peer_player.get("attack_sequence", -1)) == sequence + 3
            ):
                return False
            death_states["local"] = local_state
            death_states["peer"] = peer_state
            return True

        wait(
            f"combo_{side}_third_hit_kills_during_active_step3_on_both_clients",
            lethal_hit_is_current_on_both_clients,
            3,
            TIMING_POLL_SECONDS,
        )
        timing["lethal_hit_observed_elapsed_seconds"] = round(time.monotonic() - started, 3)
        death_state = death_states["local"]
        death_player = _player(death_state, owner).copy()
        death_position = _public_xyz(death_player)
        assert death_position is not None
        if side == "web":
            page.screenshot(path=str(output / "combo-browser-step3.png"))
        else:
            capture_path = output / "desktop.png"
            if capture_path.exists():
                capture_path.unlink()
            native_command("capture")
            wait("combo_native_step3_capture_saved", capture_path.is_file)
            capture_path.replace(output / "combo-native-step3.png")
        wait(
            f"combo_{side}_lethal_step3_root_continues_to_clip_end",
            lambda: (
                int(_player(read(), owner).get("activity", -1)) == 0
                and (position := _authoritative_xz(read(), owner)) is not None
                and math.dist(position, [death_position[0], death_position[2]]) > 0.2
            ),
            3,
        )
        final_state = read()
        final_player = _player(final_state, owner).copy()
        final_position = _public_xyz(final_player)
        assert final_position is not None
        wait(
            f"combo_{side}_terminal_root_render_converges_on_both_clients",
            lambda: (
                (local_render := _rendered_xz(read(), "rendered_actors", "identity", owner))
                is not None
                and (peer_render := _rendered_xz(peer_read(), "rendered_actors", "identity", owner))
                is not None
                and math.dist(local_render, [final_position[0], final_position[2]])
                <= ROOT_RENDER_TOLERANCE_M
                and math.dist(peer_render, [final_position[0], final_position[2]])
                <= ROOT_RENDER_TOLERANCE_M
            ),
            3,
        )
        step_1_history: dict = {}
        wait_for_history_evidence(
            f"combo_{side}_step1_projects_to_both_clients",
            side,
            owner,
            peer_read,
            COMBO_1,
            sequence + 1,
            step_1_history,
        )
        evidence[f"{side}_step_1_observation"] = step_1_history
        for side_name in ("local", "peer"):
            action = step_1_history[side_name]["public_first"]["public_action"]
            assert action.get("attack_action_id") == first_public.get("attack_action_id")
            assert int(action.get("attack_sequence", -1)) == int(
                first_public.get("attack_sequence", -2)
            )
            assert int(action.get("action_started_at_us", 0)) == int(
                first_public.get("action_started_at_us", -1)
            )
            assert int(action.get("action_ends_at_us", 0)) == int(
                first_public.get("action_ends_at_us", -1)
            )
        wait_for_history_evidence(
            f"combo_{side}_step2_projects_to_both_clients",
            side,
            owner,
            peer_read,
            COMBO_2,
            sequence + 2,
            step_2_observation,
        )
        evidence[f"{side}_step_2_observation"] = step_2_observation
        step_3_observation: dict = {}
        wait_for_history_evidence(
            f"combo_{side}_step3_projects_to_both_clients",
            side,
            owner,
            peer_read,
            COMBO_3,
            sequence + 3,
            step_3_observation,
        )
        evidence[f"{side}_step_3_observation"] = step_3_observation
        health_history: dict[str, list[int]] = {}

        def both_health_histories_are_complete() -> bool:
            health_history["local"] = _monster_health_history(read(), target_id, life)
            health_history["peer"] = _monster_health_history(peer_read(), target_id, life)
            return all(
                health_history.get(name)
                == [before_health, before_health - 35, before_health - 70, 0]
                for name in ("local", "peer")
            )

        wait(
            f"combo_{side}_public_health_history_retains_all_three_hits_on_both_clients",
            both_health_histories_are_complete,
            3,
            TIMING_POLL_SECONDS,
        )
        evidence[f"{side}_public_health_history"] = health_history
        action_histories: dict[str, dict] = {
            COMBO_1: step_1_history,
            COMBO_2: step_2_observation,
            COMBO_3: step_3_observation,
        }
        assert collect_history_evidence(
            side,
            owner,
            peer_read,
            COMBO_1,
            sequence + 1,
            action_histories[COMBO_1],
        )
        # Refresh all retained samples after the terminal endpoint has arrived.
        for action_id, action_sequence in (
            (COMBO_2, sequence + 2),
            (COMBO_3, sequence + 3),
        ):
            assert collect_history_evidence(
                side,
                owner,
                peer_read,
                action_id,
                action_sequence,
                action_histories[action_id],
            )
        root_segments = [
            validate_root_segment(
                "combo_1",
                COMBO_1,
                COMBO_1_DURATION_US,
                first_public,
                int(second["action_started_at_us"]),
                second,
            ),
            validate_root_segment(
                "combo_2",
                COMBO_2,
                COMBO_2_DURATION_US,
                second,
                int(third["action_started_at_us"]),
                third,
            ),
            validate_root_segment(
                "combo_3",
                COMBO_3,
                COMBO_3_DURATION_US,
                third,
                int(third["action_ends_at_us"]),
                final_player,
            ),
        ]
        root_histories = {
            action_id: validate_action_history(
                action_id.rsplit(".", 1)[-1],
                action_id,
                start_action,
                root_segments[index]["observed_along_m"],
                action_histories[action_id],
            )
            for index, (action_id, start_action) in enumerate(
                ((COMBO_1, first_public), (COMBO_2, second), (COMBO_3, third))
            )
        }
        return {
            "side": side,
            "first_ack": first_ack,
            "queue_ack": queued_ack,
            "renewal_ack": renewal_ack,
            "third_queue_ack": third_ack,
            "combo_2_renewal_ack": second_renewal_ack,
            "combo_1": step_1_history,
            "combo_2": step_2_observation,
            "combo_3": step_3_observation,
            "death": _action_summary(death_state, owner),
            "terminal": _action_summary(final_state, owner),
            "root_segments": root_segments,
            "root_histories": root_histories,
            "transition_after_combo_1_us": transition_us,
            "transition_after_combo_2_us": transition_2_us,
            "queue_receipt_after_combo_1_us": queue_elapsed_us,
            "queue_receipt_after_combo_2_us": third_queue_elapsed_us,
            "health": [before_health, before_health - 35, before_health - 70, 0],
            "public_health_history": health_history,
        }

    def finish_life(side: str, owner: str, peer_read) -> int:
        read = web if side == "web" else desktop
        old = _monster(read())
        old_life = int(old["life_sequence"])
        remaining = int(old["health"])
        swing = 0
        while remaining > 0:
            wait(
                f"combo_{side}_activity_finishes_before_cleanup_swing_{swing + 1}",
                lambda: int(_player(read(), owner).get("activity", -1)) == 0,
                3,
            )
            press_space(side)
            expected = max(0, remaining - 35)
            wait(
                f"combo_{side}_ordinary_cleanup_swing_{swing + 1}_deals_35",
                lambda expected=expected: (
                    int(_monster(read())["life_sequence"]) == old_life
                    and int(_monster(read())["health"]) == expected
                    and int(_monster(peer_read())["health"]) == expected
                ),
                4,
            )
            remaining = expected
            swing += 1
        wait(
            f"combo_{side}_ordinary_cleanup_kills_life",
            lambda: (
                int(_monster(read())["life_sequence"]) == old_life
                and int(_monster(read())["health"]) == 0
                and int(_monster(peer_read())["health"]) == 0
            ),
            4,
        )
        move_safe(side, owner)

        def respawned() -> bool:
            local, peer = _monster(read()), _monster(peer_read())
            return (
                int(local["life_sequence"]) == int(peer["life_sequence"]) == old_life + 1
                and int(local["health"])
                == int(local["max_health"])
                == int(peer["health"])
                == DOG_MAX_HEALTH
            )

        wait(
            f"combo_{side}_next_chain_uses_natural_fresh_life",
            respawned,
            DOG_RESPAWN_TIMEOUT_SECONDS,
        )
        return old_life + 1

    def run_cancel(label: str, mutate) -> dict:
        before_state = web()
        dog = _monster(before_state)
        before_health = int(dog["health"])
        position = _authoritative_xz(before_state, web_id)
        assert before_health >= 35 and position is not None
        assert _intent_matches(
            before_state.get("combat_target", {}), int(dog["id"]), int(dog["life_sequence"])
        )
        assert math.dist(position, [float(dog["x"]), float(dog["z"])]) < 2.8, (
            "Cancellation proof must begin within the ordinary valid hit fixture"
        )
        sequence = int(_player(before_state, web_id).get("attack_sequence", 0))
        ack_sequence = int(last_attack_ack("web").get("sequence", 0))
        sent_at = time.monotonic()
        press_space("web")
        first_ack = wait_for_ack("web", ack_sequence, True)
        first_ack_observed_at = time.monotonic()
        timing = {
            "side": "web",
            "kind": "cancellation_" + label,
            "first_command_elapsed_seconds": round(sent_at - started, 3),
            "first_ack_observed_elapsed_seconds": round(first_ack_observed_at - started, 3),
            "first_ack_observation_after_command_seconds": round(
                first_ack_observed_at - sent_at, 3
            ),
            "first_ack": first_ack,
        }
        timing_attempts.append(timing)
        deadline = first_ack_observed_at + FOLLOWUP_AFTER_FIRST_ACK_SECONDS
        timing["followup_deadline_elapsed_seconds"] = round(deadline - started, 3)
        ack_sequence = int(first_ack["sequence"])
        first_public = first_ack.get("public_action", {})
        assert first_public.get("attack_action_id") == COMBO_1
        assert int(first_public.get("attack_sequence", -1)) == sequence + 1
        time.sleep(max(0.0, deadline - time.monotonic()))
        followup_sent_at = time.monotonic()
        timing["followup_command_elapsed_seconds"] = round(followup_sent_at - started, 3)
        timing["followup_command_after_first_ack_seconds"] = round(
            followup_sent_at - first_ack_observed_at, 3
        )
        timing["followup_command_lateness_seconds"] = round(
            max(0.0, followup_sent_at - deadline), 3
        )
        press_space("web", False)
        ack = wait_for_ack("web", ack_sequence, True)
        queue_ack_observed_at = time.monotonic()
        timing["queue_ack"] = ack
        timing["queue_ack_observed_elapsed_seconds"] = round(queue_ack_observed_at - started, 3)
        timing["queue_ack_observation_after_followup_seconds"] = round(
            queue_ack_observed_at - followup_sent_at, 3
        )
        assert ack.get("public_action", {}).get("attack_action_id") == COMBO_1
        assert int(ack.get("public_action", {}).get("attack_sequence", -1)) == sequence + 1
        queue_elapsed_us = int(ack.get("reducer_timestamp_us", 0)) - int(
            ack.get("public_action", {}).get("action_started_at_us", 0)
        )
        assert COMBO_1_PRE_US < queue_elapsed_us <= COMBO_1_DIRECT_US, (
            "Cancellation setup must first prove a valid queued follow-up receipt"
        )
        timing["queue_receipt_after_combo_1_us"] = queue_elapsed_us
        mutation_xyz = _public_xyz(ack.get("public_action", {}))
        assert mutation_xyz is not None
        mutation_position = [mutation_xyz[0], mutation_xyz[2]]
        mutation_dispatch_started_at = time.monotonic()
        mutation_result = mutate(sequence + 1, before_state)
        mutation_sent_at = float(mutation_result["input_sent_at"])
        cleanup = mutation_result.get("cleanup")
        timing["mutation_dispatch_started_elapsed_seconds"] = round(
            mutation_dispatch_started_at - started, 3
        )
        timing["mutation_sent_elapsed_seconds"] = round(mutation_sent_at - started, 3)
        timing["mutation_sent_after_queue_ack_observation_seconds"] = round(
            mutation_sent_at - queue_ack_observed_at, 3
        )
        timing["mutation_setup_seconds"] = round(mutation_sent_at - mutation_dispatch_started_at, 3)
        try:
            time.sleep(1.4)
        finally:
            if callable(cleanup):
                cleanup()
        step_1_history: dict = {}
        wait_for_history_evidence(
            f"combo_{label}_step1_history_projects_to_both_clients_after_mutation",
            "web",
            web_id,
            desktop,
            COMBO_1,
            sequence + 1,
            step_1_history,
        )
        evidence[f"{label}_step_1_observation"] = step_1_history
        for side_name in ("local", "peer"):
            action = step_1_history[side_name]["public_first"]["public_action"]
            assert action.get("attack_action_id") == first_public.get("attack_action_id")
            assert int(action.get("attack_sequence", -1)) == int(
                first_public.get("attack_sequence", -2)
            )
            assert int(action.get("action_started_at_us", 0)) == int(
                first_public.get("action_started_at_us", -1)
            )
            assert int(action.get("action_ends_at_us", 0)) == int(
                first_public.get("action_ends_at_us", -1)
            )
        cancellation_states = {"local": web(), "peer": desktop()}
        combo_2_history = {
            side_name: _action_history(
                cancellation_states[side_name], web_id, COMBO_2, sequence + 2
            )
            for side_name in ("local", "peer")
        }
        assert all(not rows for rows in combo_2_history.values()), (
            f"Accepted {label} cancellation must prevent exact-sequence combo_2 "
            "on both authoritative subscription histories"
        )
        mutation_heading = float(ack.get("public_action", {}).get("heading", math.nan))
        assert math.isfinite(mutation_heading)
        root_progress: dict[str, float] = {}
        for side_name in ("local", "peer"):
            samples = [
                position
                for entry in step_1_history[side_name]["public_samples"]
                if int(entry["public_action"].get("activity", -1)) == 2
                and (position := _public_xyz(entry["public_action"])) is not None
            ]
            assert samples, (
                f"{side_name} retained no active combo_1 row after the {label} queue ACK"
            )
            progress = max(
                _projected_distance(
                    mutation_position,
                    [sample[0], sample[2]],
                    mutation_heading,
                )[0]
                for sample in samples
            )
            assert progress > 0.05, (
                f"Accepted {label} cancellation must preserve the active combo_1 root "
                f"on the {side_name} subscription"
            )
            root_progress[side_name] = progress
        after_health = before_health - 35
        assert int(_monster(web())["health"]) == int(_monster(desktop())["health"]) == after_health
        return {
            "queue_ack": ack,
            "queue_receipt_after_combo_1_us": queue_elapsed_us,
            "starting_sequence": sequence,
            "action_ends_at_us": int(first_public.get("action_ends_at_us", 0)),
            "mutation_position": mutation_position,
            "active_root_rows": {
                side_name: step_1_history[side_name]["public_samples"]
                for side_name in ("local", "peer")
            },
            "active_root_progress_m": root_progress,
            "combo_2_history": combo_2_history,
            "step_1_history": step_1_history,
            "final": _action_summary(web(), web_id),
            "health": [before_health, after_health],
        }

    set_phase("equip_browser")
    equip("web", web_id)
    move_near("web", web_id)
    dog = _monster(web())
    target_id, life = int(dog["id"]), int(dog["life_sequence"])
    select("web", web_id, target_id, life)
    set_phase("browser_three_hit_chain")
    evidence["browser_chain"] = run_three_hit_chain("web", web_id, desktop)
    life = finish_life("web", web_id, desktop)

    set_phase("equip_native")
    equip("native", native_id)
    move_near("native", native_id)
    native_state = desktop()
    dog = _monster(native_state)
    assert int(dog["life_sequence"]) == life
    select("native", native_id, target_id, life)
    set_phase("native_three_hit_chain")
    evidence["native_chain"] = run_three_hit_chain("native", native_id, web)
    life = finish_life("native", native_id, web)
    unequip("native", native_id)

    set_phase("browser_cancellation_setup")
    move_near("web", web_id)
    select("web", web_id, target_id, life)
    assert _intent_matches(web().get("combat_target", {}), target_id, life)
    assert int(_monster(web())["health"]) == DOG_MAX_HEALTH

    def held_and_released_wasd(expected_sequence: int, _baseline: dict) -> dict:
        input_sent_at = time.monotonic()
        page.keyboard.down("w")

        def release() -> None:
            try:
                wait(
                    "combo_held_WASD_starts_only_after_current_root_window",
                    lambda: (
                        int(_player(web(), web_id).get("activity", -1)) == 1
                        and int(_player(web(), web_id).get("attack_sequence", -1))
                        == expected_sequence
                    ),
                    3,
                )
            finally:
                page.keyboard.up("w")
            wait(
                "combo_released_WASD_stop_is_accepted",
                lambda: int(web().get("activity", -1)) == 0,
                3,
            )

        return {"cleanup": release, "input_sent_at": input_sent_at}

    set_phase("cancel_held_released_wasd")
    evidence["held_released_wasd_cancel"] = run_cancel("held_released_WASD", held_and_released_wasd)
    assert _intent_matches(web().get("combat_target", {}), target_id, life)
    move_safe("web", web_id)
    move_near("web", web_id)
    select("web", web_id, target_id, life)

    ground_origin: list[float] = []
    ground_destination: list[float] = []

    def ground_click(_expected_sequence: int, _baseline: dict) -> dict:
        nonlocal ground_destination, ground_origin
        projection = web_player_projection(web_id)
        player_position = _public_xyz(projection["player"])
        ground_origin = (
            [player_position[0], player_position[2]] if player_position is not None else []
        )
        assert ground_origin
        ground = projection.get("ground_pick", {})
        point = ground.get("screen", [])
        world = ground.get("world", [])
        assert (
            ground.get("available") is True
            and isinstance(point, list)
            and len(point) == 2
            and all(isinstance(value, (int, float)) and math.isfinite(value) for value in point)
            and isinstance(world, list)
            and len(world) == 3
            and all(isinstance(value, (int, float)) and math.isfinite(value) for value in world)
        ), "Ground cancellation requires a finite ray-verified projected point"
        ground_destination = [float(world[0]), float(world[2])]
        input_sent_at = time.monotonic()
        evidence["ground_click_intent"] = {
            "observed_at_elapsed_seconds": round(input_sent_at - started, 3),
            "snapshot_player_xz": ground_origin,
            "screen": [float(point[0]), float(point[1])],
            "world": [float(value) for value in world],
        }
        page.mouse.click(float(point[0]), float(point[1]))
        return {"input_sent_at": input_sent_at}

    set_phase("cancel_ground_click")
    ground_cancel = run_cancel("ground_click", ground_click)
    evidence["ground_cancel"] = ground_cancel
    assert _intent_matches(web().get("combat_target", {}), target_id, life)
    assert ground_destination
    ground_locomotion: dict[str, dict] = {}
    expected_ground_sequence = int(ground_cancel["starting_sequence"]) + 1
    for side_name in ("local", "peer"):
        entries = ground_cancel["step_1_history"][side_name]["public_samples"]
        root_indices = [
            index
            for index, entry in enumerate(entries)
            if int(entry["public_action"].get("activity", -1)) == 2
            and int(entry["public_action"].get("attack_sequence", -1)) == expected_ground_sequence
        ]
        movement = [
            (index, entry)
            for index, entry in enumerate(entries)
            if int(entry["public_action"].get("activity", -1)) == 1
            and int(entry["public_action"].get("attack_sequence", -1)) == expected_ground_sequence
        ]
        positions_3d = [_public_xyz(entry["public_action"]) for _, entry in movement]
        assert root_indices, (
            f"{side_name} retained no active combo_1 root row for ground cancellation"
        )
        assert len(positions_3d) >= 2 and all(position is not None for position in positions_3d), (
            f"{side_name} retained fewer than two valid post-action locomotion rows"
        )
        assert movement[0][0] > root_indices[-1], (
            f"{side_name} locomotion history did not follow its final active-root row "
            "in subscription callback order"
        )
        positions = [[position[0], position[2]] for position in positions_3d]
        distinct_m = max(math.dist(first, second) for first in positions for second in positions)
        destination_progress_m = math.dist(positions[0], ground_destination) - math.dist(
            positions[-1], ground_destination
        )
        assert distinct_m > 0.05 and destination_progress_m > 0.05, (
            "Accepted ground click must start ordinary movement toward its world point "
            "after the current root action ends on both subscriptions"
        )
        ground_locomotion[side_name] = {
            "final_root_history_index": root_indices[-1],
            "first": movement[0][1],
            "first_history_index": movement[0][0],
            "last": movement[-1][1],
            "last_history_index": movement[-1][0],
            "distinct_m": distinct_m,
            "destination_progress_m": destination_progress_m,
        }
    ground_cancel["ground_origin"] = ground_origin
    ground_cancel["ground_destination"] = ground_destination
    ground_cancel["post_action_locomotion"] = ground_locomotion
    move_near("web", web_id)
    life = finish_life("web", web_id, desktop)
    move_near("web", web_id)
    select("web", web_id, target_id, life)

    def clear_target(_expected_sequence: int, baseline: dict) -> dict:
        close = baseline.get("ui", {}).get("target", {}).get("close_center", [])
        assert len(close) == 2
        input_sent_at = time.monotonic()
        page.mouse.click(float(close[0]), float(close[1]))
        wait(
            "combo_target_clear_is_accepted_after_queue_ack", lambda: not web().get("combat_target")
        )
        return {"input_sent_at": input_sent_at}

    set_phase("cancel_target_clear")
    evidence["clear_cancel"] = run_cancel("target_clear", clear_target)
    assert not web().get("combat_target")

    set_phase("disconnect_stops_active_root")
    move_safe("web", web_id)
    disconnect_dog_health = int(_monster(web())["health"])
    dog_home_stable_since: float | None = None
    dog_home_samples: list[dict] = []

    def dog_is_home_outside_fallback_reach() -> bool:
        nonlocal dog_home_stable_since
        state = web()
        dog = _monster(state)
        dog_position = [float(dog["x"]), float(dog["z"])]
        player_position = _authoritative_xz(state, web_id)
        rendered_dog = _rendered_xz(state, "rendered_monsters", "row_id", int(dog["id"]))
        separation = (
            math.dist(player_position, dog_position) if player_position is not None else None
        )
        valid = (
            int(dog["health"]) == disconnect_dog_health
            and int(dog["activity"]) != 1
            and math.dist(dog_position, DOG_HOME) <= 0.25
            and player_position is not None
            and separation is not None
            and separation > PLAYER_ATTACK_RANGE_M
            and rendered_dog is not None
            and math.dist(dog_position, rendered_dog) <= ROOT_RENDER_TOLERANCE_M
        )
        now = time.monotonic()
        dog_home_samples.append(
            {
                "elapsed_seconds": round(now - started, 3),
                "valid": valid,
                "health": int(dog["health"]),
                "activity": int(dog["activity"]),
                "authoritative_xz": dog_position,
                "rendered_xz": rendered_dog,
                "player_xz": player_position,
                "separation_m": separation,
            }
        )
        del dog_home_samples[:-24]
        if not valid:
            dog_home_stable_since = None
            return False
        if dog_home_stable_since is None:
            dog_home_stable_since = now
            return False
        return now - dog_home_stable_since >= 0.5

    wait(
        "combo_disconnect_fixture_dog_is_home_outside_fallback_reach",
        dog_is_home_outside_fallback_reach,
        15,
    )
    disconnect_start_state = web()
    disconnect_start_position = _authoritative_xz(disconnect_start_state, web_id)
    assert disconnect_start_position is not None
    disconnect_sequence = int(_player(disconnect_start_state, web_id).get("attack_sequence", 0))
    disconnect_ack_sequence = int(last_attack_ack("web").get("sequence", 0))
    press_space("web")
    disconnect_attack_ack = wait_for_ack("web", disconnect_ack_sequence, True)
    assert (
        disconnect_attack_ack.get("public_action", {}).get("attack_action_id") == COMBO_1
        and int(disconnect_attack_ack.get("public_action", {}).get("attack_sequence", -1))
        == disconnect_sequence + 1
        and not disconnect_start_state.get("combat_target")
    )

    def targetless_root_advanced() -> bool:
        row = web_player_projection(web_id)["player"]
        point_3d = _public_xyz(row)
        point = [point_3d[0], point_3d[2]] if point_3d is not None else None
        return (
            int(row.get("activity", -1)) == 2
            and point is not None
            and math.dist(point, disconnect_start_position) > 0.15
        )

    wait(
        "combo_targetless_root_advances_before_disconnect",
        targetless_root_advanced,
        2,
        TIMING_POLL_SECONDS,
    )
    before_disconnect_row = web_player_projection(web_id)["player"]
    before_disconnect_3d = _public_xyz(before_disconnect_row)
    assert before_disconnect_3d is not None
    before_disconnect = [before_disconnect_3d[0], before_disconnect_3d[2]]
    assert (
        int(before_disconnect_row.get("activity", -1)) == 2
        and before_disconnect_row.get("attack_action_id") == COMBO_1
        and int(before_disconnect_row.get("attack_sequence", -1)) == disconnect_sequence + 1
        and math.dist(before_disconnect, disconnect_start_position) > 0.15
    ), "Disconnect must be sent while the exact targetless root action is still active"
    before_disconnect_observed_at = time.monotonic()
    web_command("disconnect")
    wait(
        "combo_disconnect_during_root_removes_presence",
        lambda: web().get("connection_state") == "disconnected" and not _player(desktop(), web_id),
        3,
    )
    disconnect_observed_at = time.monotonic()
    peer_after_removal = desktop()
    pre_removal_rows = _action_history(peer_after_removal, web_id, COMBO_1, disconnect_sequence + 1)
    assert pre_removal_rows, (
        "Peer history must retain the disconnecting action's final subscribed online row"
    )
    peer_pre_removal_action = pre_removal_rows[-1]["public_action"]
    peer_pre_removal_position = _public_xyz(peer_pre_removal_action)
    assert (
        peer_pre_removal_position is not None
        and int(peer_pre_removal_action.get("activity", -1)) == 2
        and int(peer_pre_removal_action.get("attack_sequence", -1)) == disconnect_sequence + 1
    ), "Peer history's final pre-removal row must be the exact active root action"
    time.sleep(1.2)
    web_command("reconnect")
    wait(
        "combo_reconnect_after_root_is_idle_without_target",
        lambda: (
            web().get("connection_state") == "connected"
            and web().get("identity") == web_id
            and int(_player(web(), web_id).get("activity", -1)) == 0
            and not web().get("combat_target")
            and bool(_player(desktop(), web_id))
        ),
        60,
    )
    reconnect_state = web()
    reconnect_position_3d = _public_xyz(_player(reconnect_state, web_id))
    assert reconnect_position_3d is not None
    reconnect_position = [reconnect_position_3d[0], reconnect_position_3d[2]]
    reconnect_jump_m = math.dist(peer_pre_removal_position, reconnect_position_3d)
    assert reconnect_jump_m <= ROOT_PUBLIC_TOLERANCE_M, (
        "Reconnect position differs from the peer's final exact subscribed online root row"
    )
    time.sleep(0.6)
    stable_reconnect_position_3d = _public_xyz(_player(web(), web_id))
    assert stable_reconnect_position_3d is not None
    stable_reconnect_position = [
        stable_reconnect_position_3d[0],
        stable_reconnect_position_3d[2],
    ]
    assert math.dist(reconnect_position_3d, stable_reconnect_position_3d) <= 0.02, (
        "Reconnect must not replay the disconnected action's remaining root"
    )
    assert int(_monster(web())["health"]) == disconnect_dog_health and not web().get(
        "combat_target"
    ), "The out-of-reach targetless disconnect action must not hit or select the Wild Dog"
    evidence["disconnect_root"] = {
        "attack_ack": disconnect_attack_ack,
        "dog_home_samples": dog_home_samples,
        "dog_health": disconnect_dog_health,
        "start_xz": disconnect_start_position,
        "last_observed_before_disconnect_xz": before_disconnect,
        "peer_last_online_action": peer_pre_removal_action,
        "peer_last_online_xyz": peer_pre_removal_position,
        "reconnected_xyz": reconnect_position_3d,
        "reconnected_xz": reconnect_position,
        "stable_reconnected_xyz": stable_reconnect_position_3d,
        "stable_reconnected_xz": stable_reconnect_position,
        "reconnect_jump_m": reconnect_jump_m,
        "position_tolerance_m": ROOT_PUBLIC_TOLERANCE_M,
        "disconnect_observation_seconds": round(
            disconnect_observed_at - before_disconnect_observed_at, 3
        ),
        "remaining_root_wait_seconds": 1.2,
    }

    set_phase("yongan_wall_collision")
    move_safe("web", web_id)

    def move_web_to(point: list[float], label: str) -> dict:
        web_command("target", x=point[0], z=point[1])
        wait(
            label,
            lambda: (
                (position := _authoritative_xz(web(), web_id)) is not None
                and math.dist(position, point) <= 0.05
            ),
            15,
        )
        web_command("stop")
        wait(label + "_stops", lambda: int(web().get("activity", -1)) == 0)
        return _player(web(), web_id).copy()

    route_rows = [
        move_web_to(point, f"combo_yongan_wall_route_{index + 1}_arrives")
        for index, point in enumerate(YONGAN_WALL_ROUTE)
    ]
    wall_start = route_rows[-1]
    wall_start_position = _public_xyz(wall_start)
    assert wall_start_position is not None
    assert abs(wall_start_position[1] - YONGAN_WALL_HEIGHT_M) <= ROOT_PUBLIC_TOLERANCE_M
    assert (
        abs(
            math.atan2(
                math.sin(float(wall_start["heading"]) + math.pi / 2),
                math.cos(float(wall_start["heading"]) + math.pi / 2),
            )
        )
        <= 0.02
    ), "Final ordinary eastward approach must establish the server heading used by wall-root QA"
    wall_sequence = int(wall_start.get("attack_sequence", 0))
    wall_ack_sequence = int(last_attack_ack("web").get("sequence", 0))
    assert not web().get("combat_target")
    press_space("web")
    wall_ack = wait_for_ack("web", wall_ack_sequence, True)
    wall_action = wall_ack.get("public_action", {})
    assert (
        wall_action.get("attack_action_id") == COMBO_1
        and int(wall_action.get("attack_sequence", -1)) == wall_sequence + 1
        and _public_xyz(wall_action) is not None
        and math.dist(_public_xyz(wall_action), wall_start_position) <= ROOT_PUBLIC_TOLERANCE_M
    )
    wall_terminal_states: dict[str, dict] = {}

    def wall_action_is_terminal_on_both_clients() -> bool:
        local_state = web()
        peer_state = desktop()
        local = _player(local_state, web_id)
        peer = _player(peer_state, web_id)
        if not (
            local.get("attack_action_id") == COMBO_1
            and int(local.get("attack_sequence", -1)) == wall_sequence + 1
            and int(local.get("activity", -1)) == 0
            and peer.get("attack_action_id") == COMBO_1
            and int(peer.get("attack_sequence", -1)) == wall_sequence + 1
            and int(peer.get("activity", -1)) == 0
        ):
            return False
        wall_terminal_states["local"] = local_state
        wall_terminal_states["peer"] = peer_state
        return True

    wait(
        "combo_yongan_wall_clips_targetless_root_and_consumes_remainder",
        wall_action_is_terminal_on_both_clients,
        3,
    )
    wall_histories = {
        side_name: _action_history(
            wall_terminal_states[side_name], web_id, COMBO_1, wall_sequence + 1
        )
        for side_name in ("local", "peer")
    }
    assert all(
        any(int(entry["public_action"].get("activity", -1)) == 2 for entry in rows)
        for rows in wall_histories.values()
    ), "Both clients must retain the exact active wall-root action before its terminal row"
    wall_end = _player(wall_terminal_states["local"], web_id).copy()
    peer_wall_end = _player(wall_terminal_states["peer"], web_id).copy()
    wall_end_position = _public_xyz(wall_end)
    peer_wall_end_position = _public_xyz(peer_wall_end)
    assert wall_end_position is not None and peer_wall_end_position is not None
    wall_travel = wall_end_position[0] - wall_start_position[0]
    assert (
        0.85 < wall_travel < 1.0
        and wall_travel < ROOT_ENDPOINTS_M[COMBO_1] - 0.3
        and abs(wall_end_position[2] - wall_start_position[2]) <= ROOT_PUBLIC_TOLERANCE_M
        and abs(wall_end_position[1] - YONGAN_WALL_HEIGHT_M) <= ROOT_PUBLIC_TOLERANCE_M
        and math.dist(wall_end_position, peer_wall_end_position) <= ROOT_PUBLIC_TOLERANCE_M
    ), "Authored Yongan wall must clip the full targetless combo root on both subscriptions"
    wait(
        "combo_yongan_wall_render_converges_to_clipped_public_position",
        lambda: (
            (local := _rendered_xz(web(), "rendered_actors", "identity", web_id)) is not None
            and (peer := _rendered_xz(desktop(), "rendered_actors", "identity", web_id)) is not None
            and math.dist(local, [wall_end_position[0], wall_end_position[2]])
            <= ROOT_RENDER_TOLERANCE_M
            and math.dist(peer, [wall_end_position[0], wall_end_position[2]])
            <= ROOT_RENDER_TOLERANCE_M
        ),
        3,
    )
    time.sleep(0.4)
    wall_stable = _authoritative_xz(web(), web_id)
    assert wall_stable is not None
    assert math.dist(wall_stable, [wall_end_position[0], wall_end_position[2]]) <= (
        ROOT_PUBLIC_TOLERANCE_M
    ), "Collision-discarded root must not replay after the action ends"
    evidence["yongan_wall_collision"] = {
        "route": route_rows,
        "attack_ack": wall_ack,
        "start": wall_start,
        "end": wall_end,
        "peer_end": peer_wall_end,
        "public_action_history": wall_histories,
        "stable_xz": wall_stable,
        "observed_travel_m": wall_travel,
        "unobstructed_endpoint_m": ROOT_ENDPOINTS_M[COMBO_1],
    }
    move_web_to(YONGAN_WALL_ROUTE[0], "combo_yongan_wall_route_returns_west")
    move_web_to(WEB_SAFE_POSITION, "combo_yongan_wall_route_returns_safe")

    set_phase("restore")
    unequip("web", web_id)
    move_safe("web", web_id)
    move_safe("native", native_id)
    assert (
        sorted(web().get("inventory", []), key=lambda row: int(row["id"]))
        == original_inventory["web"]
    )
    assert (
        sorted(desktop().get("inventory", []), key=lambda row: int(row["id"]))
        == (original_inventory["native"])
    )
    evidence["final_web"] = _action_summary(web(), web_id)
    evidence["final_native"] = _action_summary(desktop(), native_id)
    final_web_dog, final_native_dog = _monster(web()), _monster(desktop())
    assert (
        int(final_web_dog["id"]) == int(final_native_dog["id"]) == target_id
        and int(final_web_dog["life_sequence"]) == int(final_native_dog["life_sequence"]) == life
        and int(final_web_dog["health"]) == int(final_native_dog["health"]) == 65
    )
    assert not web().get("combat_target") and not desktop().get("combat_target")
    return {
        "final_life": life,
        "final_fixture": {
            "target_id": target_id,
            "life_sequence": life,
            "health": 65,
            "combat_target_cleared": True,
            "actors_parked_outside_chase": True,
        },
        "browser_chain": evidence["browser_chain"],
        "native_chain": evidence["native_chain"],
        "cancellations": {
            "held_released_wasd": evidence["held_released_wasd_cancel"],
            "ground_click": evidence["ground_cancel"],
            "target_clear": evidence["clear_cancel"],
        },
        "lifecycle": {"disconnect_during_root": evidence["disconnect_root"]},
        "collision": {"yongan_wall": evidence["yongan_wall_collision"]},
        "limits": [
            "follow-up reducer receipt timestamps are checked inside each source pre/direct window; exact boundary and collision math remains server-test evidence",
            "queue acceptance is the exact next typed reducer ACK while the preceding action remains public",
            "the client never projects queue state or starts combo_2/combo_3 optimistically",
            "public action history uses subscribed rows; its server_time_us is the preceding subscribed clock and is diagnostic rather than a position timestamp",
            "rendered history is independent visual evidence and can lag its public row during interpolation",
            "fixture approach waits for the server Wild Dog to settle at home before one ordinary move intent; it is not client auto-chase evidence",
            "the same Yongan export follows a source-reviewed ordinary waypoint route to one authored town wall and observes clipped targetless root travel; path planning is not inferred",
            "target-clear cancellation deliberately leaves the disposable dog at 65 HP; the following actor smoke is presentation-only with both actors out of range",
            "one source-derived three-step Sword+0 prefix with linear endpoint root approximation; no combo_4, Granny within-cycle/blend parity, area attacks, or PvP",
        ],
    }
