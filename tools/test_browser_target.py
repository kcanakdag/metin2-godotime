"""Exported pointer and keyboard checks for protocol-9 combat targeting."""

from __future__ import annotations

import math
import time

from browser_snapshot import POSITION_VALID, subscribed_player_position

DOG_MAX_HEALTH = 100
DOG_RESPAWN_US = 12_000_000
DOG_RESPAWN_TIMEOUT_SECONDS = 16
DOG_HOME = [675.0, 575.0]
PEER_SAFE_POSITION = [650.0, 575.0]
WEB_SAFE_POSITION = [657.0, 575.0]
PLAYER_NORMAL_ATTACK_ID = "actor.player.warrior-male.general.normal_attack.v1"


def _monster(snapshot: dict) -> dict:
    rows = snapshot.get("monsters", [])
    assert isinstance(rows, list) and len(rows) == 1, (
        "Targeting export QA requires the normal one-Wild-Dog Yongan fixture"
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


def _presentation(snapshot: dict, target_id: int) -> dict:
    return next(
        (
            row
            for row in snapshot.get("monster_presentations", [])
            if int(row.get("row_id", 0)) == target_id
        ),
        {},
    )


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


def _intent_matches(value: dict, target_id: int, life: int) -> bool:
    return (
        isinstance(value, dict)
        and int(value.get("target_id", 0)) == target_id
        and int(value.get("target_life_sequence", -1)) == life
    )


def _pick(snapshot: dict, target_id: int, life: int) -> list[float] | None:
    presentation = _presentation(snapshot, target_id)
    value = presentation.get("pick", {})
    if not isinstance(value, dict):
        return None
    point = value.get("screen", [])
    if (
        not value.get("available", False)
        or not _intent_matches(value, target_id, life)
        or not isinstance(point, list)
        or len(point) != 2
        or not all(isinstance(number, (int, float)) and math.isfinite(number) for number in point)
    ):
        return None
    return [float(point[0]), float(point[1])]


def _effect_matches(presentation: dict, field: str, effect_id: str, layers: int) -> bool:
    effect = presentation.get(field, {})
    return (
        isinstance(effect, dict)
        and effect.get("configured") is True
        and effect.get("visible") is True
        and effect.get("effect_id") == effect_id
        and int(effect.get("layer_count", 0)) == layers
        and int(effect.get("frame", -1)) >= 0
    )


def _effect_hidden(presentation: dict, field: str) -> bool:
    effect = presentation.get(field, {})
    return not effect or (isinstance(effect, dict) and effect.get("visible") is False)


def _effect_diagnostic(value) -> dict:
    if not isinstance(value, dict):
        return {"invalid_type": type(value).__name__}
    return {
        key: value.get(key)
        for key in ("configured", "visible", "effect_id", "frame", "layer_count")
    }


def _target_board_matches(snapshot: dict, target_id: int, life: int, health: int) -> bool:
    board = snapshot.get("ui", {}).get("target", {})
    return (
        board.get("visible") is True
        and int(board.get("target_id", 0)) == target_id
        and int(board.get("target_life_sequence", -1)) == life
        and board.get("display_name") == "Lv.1 Wild Dog"
        and int(board.get("health", -1)) == health
        and int(board.get("max_health", -1)) == DOG_MAX_HEALTH
        and int(board.get("action_count", 0)) == 1
        and math.isclose(float(board.get("gauge_fill_max_width", -1)), 106.0, abs_tol=0.05)
        and math.isclose(
            float(board.get("gauge_fill_width", -1)), 106.0 * health / DOG_MAX_HEALTH, abs_tol=0.05
        )
    )


def exercise_targeting(
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
    """Exercise target UI using exported-client input and ordinary navigation only."""

    started = time.monotonic()
    timings: dict[str, float] = {}
    evidence: dict[str, dict] = {}
    phase = "initial"
    trace: list[dict] = []
    pointer_inputs: list[dict] = []
    latest: dict[str, dict] = {}
    last_fingerprints: dict[str, str] = {}
    diagnostics.clear()
    diagnostics.update(
        {
            "phase": phase,
            "latest": latest,
            "trace": trace,
            "pointer_inputs": pointer_inputs,
            "evidence": evidence,
        }
    )

    def set_phase(value: str) -> None:
        nonlocal phase
        phase = value
        diagnostics["phase"] = value
        diagnostics["elapsed_seconds"] = round(time.monotonic() - started, 3)

    def observe(side: str, snapshot: dict) -> None:
        rows = snapshot.get("monsters")
        monsters = rows if isinstance(rows, list) else []
        presentations = snapshot.get("monster_presentations", [])
        target_board = snapshot.get("ui", {}).get("target", {})
        own = _player(snapshot, str(snapshot.get("identity", "")))
        value = {
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "phase": phase,
            "side": side,
            "connection_state": snapshot.get("connection_state"),
            "identity": snapshot.get("identity"),
            "combat_target": snapshot.get("combat_target", {}),
            "hover_target": snapshot.get("hover_target", {}),
            "target_board": {
                key: target_board.get(key)
                for key in ("visible", "target_id", "target_life_sequence", "health")
            },
            "own_player": {
                key: own.get(key)
                for key in ("health", "max_health", "activity", "x", "z", "attack_sequence")
            },
            "monsters": [
                {
                    key: row.get(key)
                    for key in (
                        "id",
                        "life_sequence",
                        "level",
                        "health",
                        "max_health",
                        "activity",
                        "respawn_at_us",
                        "x",
                        "z",
                    )
                }
                for row in monsters
                if isinstance(row, dict)
            ],
            "presentations": [
                {
                    "row_id": row.get("row_id"),
                    "pickable": row.get("pickable"),
                    "hovered": row.get("hovered"),
                    "targeted": row.get("targeted"),
                    "pick": row.get("pick"),
                    "hover_effect": _effect_diagnostic(row.get("hover_effect", {})),
                    "target_effect": _effect_diagnostic(row.get("target_effect", {})),
                }
                for row in presentations
                if isinstance(row, dict)
            ],
        }
        latest[side] = value
        fingerprint = repr(value | {"elapsed_seconds": 0})
        if last_fingerprints.get(side) == fingerprint:
            return
        last_fingerprints[side] = fingerprint
        trace.append(value)
        del trace[:-64]

    read_web, read_desktop = web, desktop

    def web() -> dict:
        snapshot = read_web()
        observe("web", snapshot)
        return snapshot

    def desktop() -> dict:
        snapshot = read_desktop()
        observe("native", snapshot)
        return snapshot

    def mark(name: str) -> None:
        timings[name] = round(time.monotonic() - started, 3)

    def summary(snapshot: dict) -> dict:
        dog = _monster(snapshot)
        presentation = _presentation(snapshot, int(dog["id"]))
        board = snapshot.get("ui", {}).get("target", {})
        return {
            "identity": snapshot.get("identity"),
            "connection_state": snapshot.get("connection_state"),
            "combat_target": snapshot.get("combat_target", {}),
            "hover_target": snapshot.get("hover_target", {}),
            "monster": {
                key: dog.get(key)
                for key in (
                    "id",
                    "life_sequence",
                    "level",
                    "health",
                    "max_health",
                    "activity",
                    "respawn_at_us",
                    "x",
                    "z",
                )
            },
            "presentation": {
                key: presentation.get(key)
                for key in ("row_id", "pickable", "hovered", "targeted", "pick")
            }
            | {
                "hover_effect": presentation.get("hover_effect", {}),
                "target_effect": presentation.get("target_effect", {}),
            },
            "target_board": {
                key: board.get(key)
                for key in (
                    "visible",
                    "target_id",
                    "target_life_sequence",
                    "display_name",
                    "health",
                    "max_health",
                    "board_rect",
                    "close_center",
                    "action_count",
                )
            },
        }

    def authoritative_xz(snapshot: dict, identity: str) -> list[float] | None:
        status, position = subscribed_player_position(snapshot, identity)
        if status != POSITION_VALID or position is None:
            return None
        return [float(position[0]), float(position[2])]

    def last_web_select_ack() -> dict:
        rows = page.evaluate("() => JSON.parse(window.mt2SelectTargetAcks || '[]')")
        assert isinstance(rows, list)
        return rows[-1] if rows and isinstance(rows[-1], dict) else {}

    def wait_web_select_ack(
        label: str, after: int, expected_target_id: int, expected_life: int
    ) -> dict:
        found: dict = {}

        def exact_next_ack() -> bool:
            nonlocal found
            ack = last_web_select_ack()
            sequence = int(ack.get("sequence", 0))
            if sequence <= after:
                return False
            if sequence != after + 1:
                raise AssertionError("Target ACK sequence skipped the expected reducer completion")
            found = ack.copy()
            if not bool(ack.get("succeeded")):
                raise AssertionError("The exact next target selection ACK was rejected")
            if int(ack.get("reducer_timestamp_us", 0)) <= 0:
                raise AssertionError("Accepted target ACK has no typed server timestamp")
            if not _intent_matches(ack.get("combat_target", {}), expected_target_id, expected_life):
                raise AssertionError("Accepted target ACK does not retain the requested exact life")
            return True

        wait(label, exact_next_ack, 3, 0.01)
        return found

    def inject_pointer(
        label: str,
        side: str,
        action: str,
        point: list[float],
        snapshot: dict,
        evidence_point: list[float] | None,
        evidence_kind: str,
    ) -> None:
        dog = _monster(snapshot)
        requested = [float(point[0]), float(point[1])]
        pointer_inputs.append(
            {
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "phase": phase,
                "label": label,
                "side": side,
                "action": action,
                "requested_point": requested,
                "evidence_kind": evidence_kind,
                "evidence_point": evidence_point,
                "authoritative_player_xz": authoritative_xz(
                    snapshot, web_id if side == "web" else native_id
                ),
                "rendered_player_xz": _rendered_xz(
                    snapshot,
                    "rendered_actors",
                    "identity",
                    web_id if side == "web" else native_id,
                ),
                "authoritative_monster_xz": [float(dog["x"]), float(dog["z"])],
                "rendered_monster_xz": _rendered_xz(
                    snapshot, "rendered_monsters", "row_id", int(dog["id"])
                ),
                "monster_activity": int(dog["activity"]),
            }
        )
        del pointer_inputs[:-32]
        if side == "web":
            if action == "move":
                page.mouse.move(*requested)
            else:
                page.mouse.click(*requested)
            return
        native_command(
            "pointer_move" if action == "move" else "pointer_click", x=point[0], y=point[1]
        )

    def move_near_dog(command, read, identity: str, prefix: str) -> None:
        approach: dict = {"home_settle_samples": [], "movement_samples": [], "waypoints": []}
        evidence[prefix + "_approach"] = approach
        initial = read()
        dog = _monster(initial)
        player = authoritative_xz(initial, identity)
        already_near = (
            player is not None and math.dist(player, [float(dog["x"]), float(dog["z"])]) < 2.6
        )
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

            wait(prefix + "_waits_for_stable_Wild_Dog_home", dog_is_stable_at_home, 15)

        state = read()
        dog = _monster(state)
        waypoint = [float(dog["x"]), float(dog["z"])]
        approach["already_in_reach"] = already_near
        if not already_near:
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
            point = authoritative_xz(state, identity)
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
                and math.dist(point, dog_position) < 2.6
                and int(current["health"]) > 0
            )

        wait(prefix + "_reaches_live_Wild_Dog", reached, 15)
        command("stop")
        wait(prefix + "_stops_in_attack_reach", lambda: read().get("activity") == 0)

    set_phase("park_native")
    native_command("target", x=PEER_SAFE_POSITION[0], z=PEER_SAFE_POSITION[1])

    def native_is_parked() -> bool:
        point = authoritative_xz(desktop(), native_id)
        return point is not None and math.dist(point, PEER_SAFE_POSITION) < 0.5

    wait("targeting_parks_native_outside_dog_chase", native_is_parked, 12)
    native_command("stop")
    wait("targeting_native_safe_position_is_stopped", lambda: desktop().get("activity") == 0)

    set_phase("retained_fixture_restoration")
    retained_dog = _monster(web()).copy()
    restoration = {
        "required": int(retained_dog["health"]) != DOG_MAX_HEALTH,
        "initial_life_sequence": int(retained_dog["life_sequence"]),
        "initial_health": int(retained_dog["health"]),
        "ordinary_space_hits": 0,
    }
    evidence["retained_fixture_restoration"] = restoration
    if 0 < int(retained_dog["health"]) < DOG_MAX_HEALTH:
        restoration_life = int(retained_dog["life_sequence"])
        move_near_dog(web_command, web, web_id, "targeting_restoration")
        for _hit in range(4):
            if int(_monster(web())["health"]) == 0:
                break
            before = web()
            current = _monster(before)
            assert int(current["life_sequence"]) == restoration_life
            before_health = int(current["health"])
            before_sequence = int(_player(before, web_id).get("attack_sequence", 0))
            page.locator("canvas").focus()
            page.keyboard.press("Space")

            def restoration_hit_resolves(
                expected_health: int = max(0, before_health - 25),
                expected_sequence: int = before_sequence + 1,
            ) -> bool:
                state = web()
                dog = _monster(state)
                return (
                    int(dog["life_sequence"]) == restoration_life
                    and int(dog["health"]) == expected_health
                    and int(_player(state, web_id).get("attack_sequence", 0)) == expected_sequence
                )

            wait(
                "targeting_restoration_ordinary_hit_resolves",
                restoration_hit_resolves,
                4,
            )
            restoration["ordinary_space_hits"] += 1
            if int(_monster(web())["health"]) > 0:
                time.sleep(1.0)
        assert int(_monster(web())["health"]) == 0, (
            "At most four ordinary unarmed attacks must finish a damaged Wild Dog life"
        )

    if int(_monster(web())["health"]) == 0:
        dead_life = int(_monster(web())["life_sequence"])
        respawn_started = time.monotonic()

        def restoration_respawned() -> bool:
            web_dog, native_dog = _monster(web()), _monster(desktop())
            return (
                int(web_dog["life_sequence"]) == int(native_dog["life_sequence"]) == dead_life + 1
                and int(web_dog["health"])
                == int(web_dog["max_health"])
                == int(native_dog["health"])
                == DOG_MAX_HEALTH
                and int(web_dog.get("respawn_at_us", 0))
                == int(native_dog.get("respawn_at_us", 0))
                == 0
            )

        wait(
            "targeting_retained_fixture_restores_by_natural_respawn",
            restoration_respawned,
            DOG_RESPAWN_TIMEOUT_SECONDS,
        )
        restoration["natural_respawn_seconds"] = round(time.monotonic() - respawn_started, 3)
        restoration["restored_life_sequence"] = dead_life + 1
        # A fallback target created by a restoration hit is removed on death,
        # while its server-owned churn deadline intentionally survives cleanup.
        time.sleep(1.05)
    else:
        restoration["restored_life_sequence"] = int(_monster(web())["life_sequence"])
    restoration["final_health"] = int(_monster(web())["health"])

    def fresh_shared_dog() -> bool:
        web_dog = _monster(web())
        native_dog = _monster(desktop())
        return (
            int(web_dog["id"]) == int(native_dog["id"])
            and int(web_dog["life_sequence"]) == int(native_dog["life_sequence"])
            and int(web_dog["health"])
            == int(web_dog["max_health"])
            == int(native_dog["health"])
            == int(native_dog["max_health"])
            == DOG_MAX_HEALTH
            and int(web_dog.get("level", 0)) == int(native_dog.get("level", 0)) == 1
            and int(web_dog.get("respawn_at_us", 0)) == 0
        )

    set_phase("fresh_dog")
    wait("targeting_starts_on_one_fresh_authoritative_Wild_Dog", fresh_shared_dog, 16)
    set_phase("browser_approach")
    approach_before = web()
    approach_dog = _monster(approach_before)
    approach_life = int(approach_dog["life_sequence"])
    approach_attack_sequence = int(_player(approach_before, web_id).get("attack_sequence", 0))
    move_near_dog(web_command, web, web_id, "browser_targeting")

    def browser_approach_is_noncombat() -> bool:
        state = web()
        current = _monster(state)
        return (
            int(current["life_sequence"]) == approach_life
            and int(current["health"]) == DOG_MAX_HEALTH
            and int(_player(state, web_id).get("attack_sequence", 0)) == approach_attack_sequence
            and int(_player(state, web_id).get("activity", -1)) == 0
        )

    wait(
        "targeting_browser_approach_stops_without_attacking_or_damaging_dog",
        browser_approach_is_noncombat,
    )
    dog = _monster(web())
    target_id, life = int(dog["id"]), int(dog["life_sequence"])
    wait(
        "targeting_browser_has_verified_visible_pick_point",
        lambda: _pick(web(), target_id, life) is not None,
        15,
    )
    pointer_state = web()
    point = _pick(pointer_state, target_id, life)
    assert point is not None
    set_phase("browser_hover")
    inject_pointer(
        "browser_hover",
        "web",
        "move",
        point,
        pointer_state,
        _pick(pointer_state, target_id, life),
        "monster_pick",
    )

    def browser_hover_ready() -> bool:
        state = web()
        presentation = _presentation(state, target_id)
        return (
            _intent_matches(state.get("hover_target", {}), target_id, life)
            and presentation.get("hovered") is True
            and _effect_matches(presentation, "hover_effect", "effect.actor.hover.v1", 1)
            and not state.get("combat_target")
            and not state.get("ui", {}).get("target", {}).get("visible")
        )

    wait("stationary_browser_pointer_attaches_hover_only", browser_hover_ready)
    hover_before = _presentation(web(), target_id).get("hover_effect", {}).copy()

    def stationary_hover_advances() -> bool:
        state = web()
        effect = _presentation(state, target_id).get("hover_effect", {})
        return (
            _intent_matches(state.get("hover_target", {}), target_id, life)
            and effect.get("configured") is True
            and int(effect.get("frame", -1)) != int(hover_before.get("frame", -1))
        )

    wait("stationary_pointer_hover_effect_advances_without_new_input", stationary_hover_advances, 3)
    pointer_state = web()
    point = _pick(pointer_state, target_id, life)
    assert point is not None
    set_phase("browser_select")
    select_ack_sequence = int(last_web_select_ack().get("sequence", 0))
    inject_pointer(
        "browser_select",
        "web",
        "click",
        point,
        pointer_state,
        _pick(pointer_state, target_id, life),
        "monster_pick",
    )

    def browser_target_ready() -> bool:
        state = web()
        presentation = _presentation(state, target_id)
        target = state.get("combat_target", {})
        return (
            _intent_matches(target, target_id, life)
            and set(target) == {"account", "character_id", "target_id", "target_life_sequence"}
            and target.get("account") == state.get("account", {}).get("account_identity")
            and target.get("character_id") == web_id
            and _target_board_matches(state, target_id, life, DOG_MAX_HEALTH)
            and presentation.get("targeted") is True
            and _effect_matches(presentation, "target_effect", "effect.actor.target.v1", 2)
            and _effect_matches(presentation, "hover_effect", "effect.actor.hover.v1", 1)
        )

    wait("browser_canvas_click_opens_authoritative_target_presentation", browser_target_ready)
    evidence["browser_initial_select_ack"] = wait_web_select_ack(
        "browser_canvas_click_has_exact_accepted_select_ACK",
        select_ack_sequence,
        target_id,
        life,
    )
    wait(
        "peer_cannot_read_browser_private_target",
        lambda: (
            not desktop().get("combat_target")
            and not desktop().get("ui", {}).get("target", {}).get("visible")
        ),
    )
    evidence["browser_selected"] = summary(web())
    page.screenshot(path=str(output / "targeting-browser-selected.png"))

    set_phase("browser_ground_and_wasd")
    ground_state = web()
    ground_pick = ground_state.get("ground_pick", {})
    ground_point = ground_pick.get("screen", []) if isinstance(ground_pick, dict) else []
    ground_world = ground_pick.get("world", []) if isinstance(ground_pick, dict) else []
    ground_start = authoritative_xz(ground_state, web_id)
    assert (
        ground_pick.get("available") is True
        and isinstance(ground_point, list)
        and len(ground_point) == 2
        and isinstance(ground_world, list)
        and len(ground_world) == 3
        and all(isinstance(value, (int, float)) and math.isfinite(value) for value in ground_point)
        and all(isinstance(value, (int, float)) and math.isfinite(value) for value in ground_world)
        and ground_start is not None
    ), "Targeting snapshot must expose one ray-verified finite ground pick point"
    inject_pointer(
        "browser_ground_move",
        "web",
        "click",
        [float(ground_point[0]), float(ground_point[1])],
        ground_state,
        [float(ground_point[0]), float(ground_point[1])],
        "ground_pick",
    )

    def ground_click_moves_with_target() -> bool:
        state = web()
        point = authoritative_xz(state, web_id)
        return (
            point is not None
            and math.dist(point, ground_start) > 0.1
            and _intent_matches(state.get("combat_target", {}), target_id, life)
        )

    wait(
        "actual_ground_click_moves_and_preserves_authoritative_target",
        ground_click_moves_with_target,
        6,
    )
    page.keyboard.down("w")
    wasd_start = authoritative_xz(web(), web_id)

    def wasd_moved_with_target() -> bool:
        state = web()
        point = authoritative_xz(state, web_id)
        return (
            wasd_start is not None
            and point is not None
            and math.dist(point, wasd_start) > 0.2
            and _intent_matches(state.get("combat_target", {}), target_id, life)
        )

    try:
        wait(
            "targeting_WASD_moves_with_selection_retained",
            wasd_moved_with_target,
            6,
        )
    finally:
        page.keyboard.up("w")
    web_command("stop")
    wait(
        "targeting_browser_stops_with_selection_retained",
        lambda: (
            web().get("activity") == 0
            and _intent_matches(web().get("combat_target", {}), target_id, life)
        ),
    )

    def settled_browser_pick(label: str) -> tuple[dict, list[float]]:
        stable_since: float | None = None
        stable_pick: list[float] | None = None
        stable_player: list[float] | None = None
        stable_dog: list[float] | None = None
        settled_state: dict = {}
        settle_evidence: dict = {
            "required_seconds": 0.5,
            "maximum_pick_drift_pixels": 1.0,
            "maximum_position_drift_meters": 0.05,
            "maximum_render_error_meters": 0.05,
            "samples": [],
        }
        evidence[label + "_pick_settle"] = settle_evidence

        def projection_is_settled() -> bool:
            nonlocal stable_since, stable_pick, stable_player, stable_dog, settled_state
            state = web()
            current_dog = _monster(state)
            own = _player(state, web_id)
            pick = _pick(state, target_id, life)
            player = authoritative_xz(state, web_id)
            rendered_player = _rendered_xz(state, "rendered_actors", "identity", web_id)
            dog_position = [float(current_dog["x"]), float(current_dog["z"])]
            rendered_dog = _rendered_xz(state, "rendered_monsters", "row_id", target_id)
            now = time.monotonic()
            valid = (
                own.get("online") is True
                and int(own.get("activity", -1)) == 0
                and int(current_dog["life_sequence"]) == life
                and int(current_dog["health"]) > 0
                and int(current_dog["activity"]) != 1
                and _intent_matches(state.get("combat_target", {}), target_id, life)
                and pick is not None
                and player is not None
                and rendered_player is not None
                and rendered_dog is not None
                and math.dist(rendered_player, player) <= 0.05
                and math.dist(rendered_dog, dog_position) <= 0.05
            )
            sample = {
                "elapsed_seconds": round(now - started, 3),
                "valid": valid,
                "pick": pick,
                "authoritative_player_xz": player,
                "rendered_player_xz": rendered_player,
                "authoritative_monster_xz": dog_position,
                "rendered_monster_xz": rendered_dog,
                "monster_activity": int(current_dog["activity"]),
            }
            settle_evidence.update(sample)
            settle_evidence["samples"].append(sample)
            del settle_evidence["samples"][:-24]
            if not valid:
                stable_since = None
                stable_pick = None
                stable_player = None
                stable_dog = None
                settle_evidence["stable_seconds"] = 0.0
                return False
            assert pick is not None and player is not None
            if (
                stable_since is None
                or stable_pick is None
                or stable_player is None
                or stable_dog is None
                or math.dist(pick, stable_pick) > 1.0
                or math.dist(player, stable_player) > 0.05
                or math.dist(dog_position, stable_dog) > 0.05
            ):
                stable_since = now
                stable_pick = pick
                stable_player = player
                stable_dog = dog_position
                settle_evidence["stable_seconds"] = 0.0
                return False
            settle_evidence["stable_seconds"] = round(now - stable_since, 3)
            if now - stable_since < 0.5:
                return False
            settled_state = state
            settle_evidence["settled_pick"] = pick
            return True

        wait(label + "_pick_and_authoritative_positions_settle", projection_is_settled, 15)
        point = _pick(settled_state, target_id, life)
        assert point is not None
        return settled_state, point

    set_phase("browser_close_reject_reselect")
    pointer_state, point = settled_browser_pick("browser_same_target_renewal")
    renewal_ack_sequence = int(last_web_select_ack().get("sequence", 0))
    inject_pointer(
        "browser_same_target_renewal",
        "web",
        "click",
        point,
        pointer_state,
        _pick(pointer_state, target_id, life),
        "monster_pick",
    )
    renewal_ack = wait_web_select_ack(
        "same_target_canvas_click_has_exact_accepted_select_ACK",
        renewal_ack_sequence,
        target_id,
        life,
    )
    renewed_at = time.monotonic()
    evidence["browser_same_target_renewal_ack"] = renewal_ack
    wait(
        "same_target_canvas_click_keeps_authoritative_target",
        lambda: _intent_matches(web().get("combat_target", {}), target_id, life),
    )
    state = web()
    close = state["ui"]["target"]["close_center"]
    before_close = authoritative_xz(state, web_id)
    errors_before = len(state.get("errors", []))
    evidence["browser_before_close"] = {
        "position": before_close,
        "state": summary(state),
        "renewal_ack": renewal_ack,
    }
    inject_pointer(
        "browser_target_close",
        "web",
        "click",
        [float(close[0]), float(close[1])],
        state,
        [float(close[0]), float(close[1])],
        "target_close_center",
    )

    def target_closed_without_movement() -> bool:
        state = web()
        point = authoritative_xz(state, web_id)
        presentation = _presentation(state, target_id)
        evidence["browser_close_observation"] = {
            "position": point,
            "position_drift_meters": (
                math.dist(point, before_close)
                if before_close is not None and point is not None
                else None
            ),
            "state": summary(state),
        }
        return (
            not state.get("combat_target")
            and not state.get("ui", {}).get("target", {}).get("visible")
            and presentation.get("targeted") is False
            and _effect_hidden(presentation, "target_effect")
            and before_close is not None
            and point is not None
            and math.dist(point, before_close) < 0.05
        )

    wait(
        "target_board_close_clears_without_movement",
        target_closed_without_movement,
    )
    assert time.monotonic() - renewed_at < 1.0, "Close/reselect deadline setup took too long"
    pointer_state = web()
    point = _pick(pointer_state, target_id, life)
    assert point is not None
    inject_pointer(
        "browser_rejected_reselect",
        "web",
        "click",
        point,
        pointer_state,
        _pick(pointer_state, target_id, life),
        "monster_pick",
    )

    def rejected_reselect_stays_clear() -> bool:
        state = web()
        presentation = _presentation(state, target_id)
        errors = state.get("errors", [])
        return (
            len(errors) > errors_before
            and errors[-1] == "Wait one second before changing combat targets."
            and not state.get("combat_target")
            and not state.get("ui", {}).get("target", {}).get("visible")
            and presentation.get("targeted") is False
            and _effect_hidden(presentation, "target_effect")
        )

    wait(
        "deadline_rejection_does_not_invent_local_target",
        rejected_reselect_stays_clear,
    )
    mark("browser_close_and_rejection")
    time.sleep(max(0.0, 1.05 - (time.monotonic() - renewed_at)))
    pointer_state = web()
    point = _pick(pointer_state, target_id, life)
    assert point is not None
    inject_pointer(
        "browser_post_deadline_reselect",
        "web",
        "click",
        point,
        pointer_state,
        _pick(pointer_state, target_id, life),
        "monster_pick",
    )
    wait(
        "browser_can_reselect_after_retained_deadline",
        lambda: _intent_matches(web().get("combat_target", {}), target_id, life),
    )
    pointer_state = web()
    close = pointer_state["ui"]["target"]["close_center"]
    inject_pointer(
        "browser_target_close_before_native",
        "web",
        "click",
        [float(close[0]), float(close[1])],
        pointer_state,
        [float(close[0]), float(close[1])],
        "target_close_center",
    )
    wait("browser_target_clears_before_native_input", lambda: not web().get("combat_target"))

    def settled_native_pick(label: str, expected_life: int) -> tuple[dict, list[float]]:
        stable_since: float | None = None
        stable_pick: list[float] | None = None
        stable_player: list[float] | None = None
        stable_dog: list[float] | None = None
        settled_state: dict = {}
        settle_evidence: dict = {
            "required_seconds": 0.5,
            "maximum_pick_drift_pixels": 1.0,
            "maximum_render_error_meters": 0.05,
            "samples": [],
        }
        evidence[f"{label}_pick_settle"] = settle_evidence

        def projection_is_settled() -> bool:
            nonlocal stable_since, stable_pick, stable_player, stable_dog, settled_state
            state = desktop()
            current_dog = _monster(state)
            own = _player(state, native_id)
            pick = _pick(state, target_id, expected_life)
            player = authoritative_xz(state, native_id)
            rendered_player = _rendered_xz(state, "rendered_actors", "identity", native_id)
            dog_position = [float(current_dog["x"]), float(current_dog["z"])]
            rendered_dog = _rendered_xz(state, "rendered_monsters", "row_id", target_id)
            now = time.monotonic()
            valid = (
                own.get("online") is True
                and int(own.get("activity", -1)) == 0
                and int(current_dog["life_sequence"]) == expected_life
                and int(current_dog["health"]) == int(current_dog["max_health"]) == DOG_MAX_HEALTH
                and int(current_dog["activity"]) != 1
                and pick is not None
                and player is not None
                and rendered_player is not None
                and rendered_dog is not None
                and math.dist(rendered_player, player) <= 0.05
                and math.dist(rendered_dog, dog_position) <= 0.05
            )
            settle_evidence.update(
                {
                    "valid": valid,
                    "pick": pick,
                    "authoritative_player_xz": player,
                    "rendered_player_xz": rendered_player,
                    "authoritative_monster_xz": dog_position,
                    "rendered_monster_xz": rendered_dog,
                    "monster_activity": int(current_dog["activity"]),
                }
            )
            settle_evidence["samples"].append(
                {
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "valid": valid,
                    "pick": pick,
                    "authoritative_player_xz": player,
                    "rendered_player_xz": rendered_player,
                    "authoritative_monster_xz": dog_position,
                    "rendered_monster_xz": rendered_dog,
                    "monster_activity": int(current_dog["activity"]),
                }
            )
            del settle_evidence["samples"][:-24]
            if not valid:
                stable_since = None
                stable_pick = None
                stable_player = None
                stable_dog = None
                settle_evidence["stable_seconds"] = 0.0
                return False
            assert pick is not None and player is not None
            if (
                stable_since is None
                or stable_pick is None
                or stable_player is None
                or stable_dog is None
                or math.dist(pick, stable_pick) > 1.0
                or math.dist(player, stable_player) > 0.05
                or math.dist(dog_position, stable_dog) > 0.05
            ):
                stable_since = now
                stable_pick = pick
                stable_player = player
                stable_dog = dog_position
                settle_evidence["stable_seconds"] = 0.0
                return False
            settle_evidence["stable_seconds"] = round(now - stable_since, 3)
            if now - stable_since < 0.5:
                return False
            settled_state = state
            settle_evidence["settled_pick"] = pick
            return True

        wait(f"{label}_native_pick_projection_settles_before_input", projection_is_settled, 15)
        point = _pick(settled_state, target_id, expected_life)
        assert point is not None
        return settled_state, point

    set_phase("native_approach_select")
    web_command("target", x=WEB_SAFE_POSITION[0], z=WEB_SAFE_POSITION[1])

    def browser_is_parked() -> bool:
        point = authoritative_xz(web(), web_id)
        return point is not None and math.dist(point, WEB_SAFE_POSITION) < 0.5

    wait(
        "targeting_parks_browser_outside_dog_chase",
        browser_is_parked,
        12,
    )
    web_command("stop")
    move_near_dog(native_command, desktop, native_id, "native_targeting")
    dog = _monster(desktop())
    life = int(dog["life_sequence"])
    pointer_state, point = settled_native_pick("initial_hover", life)
    inject_pointer(
        "native_hover",
        "native",
        "move",
        point,
        pointer_state,
        _pick(pointer_state, target_id, life),
        "settled_monster_pick",
    )

    def native_hover_ready() -> bool:
        state = desktop()
        presentation = _presentation(state, target_id)
        return (
            _intent_matches(state.get("hover_target", {}), target_id, life)
            and presentation.get("hovered") is True
            and _effect_matches(presentation, "hover_effect", "effect.actor.hover.v1", 1)
        )

    wait(
        "native_fixed_pointer_event_routes_to_hover",
        native_hover_ready,
    )
    pointer_state = desktop()
    point = _pick(pointer_state, target_id, life)
    assert point is not None
    inject_pointer(
        "native_select",
        "native",
        "click",
        point,
        pointer_state,
        _pick(pointer_state, target_id, life),
        "monster_pick",
    )

    def native_target_ready() -> bool:
        native_state, web_state = desktop(), web()
        target = native_state.get("combat_target", {})
        presentation = _presentation(native_state, target_id)
        return (
            _intent_matches(target, target_id, life)
            and set(target) == {"account", "character_id", "target_id", "target_life_sequence"}
            and target.get("account") == native_state.get("account", {}).get("account_identity")
            and target.get("character_id") == native_id
            and _target_board_matches(native_state, target_id, life, DOG_MAX_HEALTH)
            and presentation.get("targeted") is True
            and _effect_matches(presentation, "target_effect", "effect.actor.target.v1", 2)
            and _effect_matches(presentation, "hover_effect", "effect.actor.hover.v1", 1)
            and not web_state.get("combat_target")
        )

    wait(
        "native_fixed_pointer_click_selects_through_world_input",
        native_target_ready,
    )
    evidence["native_selected"] = summary(desktop())
    native_command("capture")
    native_capture = output / "desktop.png"
    wait("native_target_presentation_capture_saved", native_capture.is_file)
    native_capture.replace(output / "targeting-native-selected.png")

    set_phase("native_selected_attacks")
    initial_health = int(_monster(web())["health"])
    initial_sequence = int(_player(desktop(), native_id).get("attack_sequence", 0))
    assert initial_health == DOG_MAX_HEALTH
    native_command("space")

    def selected_hit_resolves(expected_health: int, expected_sequence: int) -> bool:
        peer_dog = _monster(web())
        actor = _player(desktop(), native_id)
        return (
            int(peer_dog["life_sequence"]) == life
            and int(peer_dog["health"]) == expected_health
            and int(actor.get("attack_sequence", 0)) == expected_sequence
            and actor.get("attack_action_id") == PLAYER_NORMAL_ATTACK_ID
        )

    wait(
        "native_fixed_Space_damages_selected_target_once_on_peer",
        lambda: selected_hit_resolves(initial_health - 25, initial_sequence + 1),
        4,
    )
    wait(
        "target_board_tracks_peer_observed_authoritative_damage",
        lambda: _target_board_matches(desktop(), target_id, life, initial_health - 25),
    )
    for hit_index in range(2, 5):
        time.sleep(1.0)
        sequence = int(_player(desktop(), native_id).get("attack_sequence", 0))
        native_command("space")
        wait(
            f"selected_target_hit_{hit_index}_resolves_once",
            lambda index=hit_index, expected_sequence=sequence + 1: selected_hit_resolves(
                max(0, DOG_MAX_HEALTH - index * 25), expected_sequence
            ),
            4,
        )

    def dead_target_cleared() -> bool:
        web_dog, native_dog = _monster(web()), _monster(desktop())
        presentation = _presentation(desktop(), target_id)
        return (
            int(web_dog["life_sequence"]) == int(native_dog["life_sequence"]) == life
            and int(web_dog["health"]) == int(native_dog["health"]) == 0
            and not desktop().get("combat_target")
            and not desktop().get("hover_target")
            and not desktop().get("ui", {}).get("target", {}).get("visible")
            and presentation.get("targeted") is False
            and presentation.get("hovered") is False
            and _effect_hidden(presentation, "target_effect")
            and _effect_hidden(presentation, "hover_effect")
        )

    set_phase("target_death")
    wait("target_death_detaches_old_life_target_and_hover", dead_target_cleared)
    dead_at = time.monotonic()
    dead_dog = _monster(desktop())
    assert int(dead_dog["respawn_at_us"]) - int(dead_dog["action_started_at_us"]) == DOG_RESPAWN_US
    evidence["dead_life"] = summary(desktop())
    page.screenshot(path=str(output / "targeting-dead-cleared.png"))
    pointer_state = desktop()
    inject_pointer(
        "native_clear_dead_life_hover",
        "native",
        "move",
        [1.0, 1.0],
        pointer_state,
        None,
        "intentional_empty_corner",
    )

    def fresh_life_has_no_inherited_target() -> bool:
        web_dog, native_dog = _monster(web()), _monster(desktop())
        new_life = int(native_dog["life_sequence"])
        presentation = _presentation(desktop(), target_id)
        return (
            new_life == life + 1
            and int(web_dog["life_sequence"]) == new_life
            and int(web_dog["health"])
            == int(native_dog["health"])
            == int(native_dog["max_health"])
            == DOG_MAX_HEALTH
            and not desktop().get("combat_target")
            and not desktop().get("hover_target")
            and presentation.get("targeted") is False
            and presentation.get("hovered") is False
            and not presentation.get("target_effect")
            and not presentation.get("hover_effect")
        )

    set_phase("production_respawn")
    wait(
        "production_respawn_new_life_inherits_no_target_or_hover",
        fresh_life_has_no_inherited_target,
        DOG_RESPAWN_TIMEOUT_SECONDS,
    )
    respawn_elapsed = time.monotonic() - dead_at
    assert 11.0 <= respawn_elapsed < DOG_RESPAWN_TIMEOUT_SECONDS
    timings["tested_life_production_respawn"] = round(respawn_elapsed, 3)
    life += 1
    evidence["fresh_life"] = summary(desktop())
    mark("production_respawn")

    set_phase("character_leave_reentry")
    pointer_state, point = settled_native_pick("fresh_life_selection", life)
    inject_pointer(
        "native_select_fresh_life",
        "native",
        "click",
        point,
        pointer_state,
        _pick(pointer_state, target_id, life),
        "monster_pick",
    )
    wait(
        "native_selects_fresh_life_before_character_leave",
        lambda: _intent_matches(desktop().get("combat_target", {}), target_id, life),
    )
    native_command("leave")
    wait(
        "character_leave_clears_target_projection_and_presence",
        lambda: (
            desktop().get("connection_state") == "lobby"
            and not desktop().get("combat_target")
            and not desktop().get("ui", {}).get("target", {}).get("visible")
            and not any(row.get("identity") == native_id for row in web().get("player_rows", []))
        ),
    )
    native_command("enter")

    def reentry_has_no_target() -> bool:
        state = desktop()
        presentation = _presentation(state, target_id)
        return (
            state.get("connection_state") == "connected"
            and state.get("identity") == native_id
            and not state.get("combat_target")
            and _effect_hidden(presentation, "target_effect")
        )

    wait(
        "character_reentry_does_not_restore_target",
        reentry_has_no_target,
        60,
    )
    time.sleep(1.05)
    pointer_state, point = settled_native_pick("post_reentry_selection", life)
    inject_pointer(
        "native_select_before_reconnect",
        "native",
        "click",
        point,
        pointer_state,
        _pick(pointer_state, target_id, life),
        "monster_pick",
    )
    wait(
        "native_selects_before_account_reconnect",
        lambda: _intent_matches(desktop().get("combat_target", {}), target_id, life),
    )
    set_phase("account_reconnect")
    native_command("disconnect")
    wait(
        "targeting_disconnect_clears_private_projection",
        lambda: (
            desktop().get("connection_state") == "disconnected"
            and not desktop().get("combat_target")
        ),
    )
    native_command("reconnect")

    def reconnect_has_no_target() -> bool:
        state = desktop()
        presentation = _presentation(state, target_id)
        return (
            state.get("connection_state") == "connected"
            and state.get("identity") == native_id
            and not state.get("combat_target")
            and not state.get("ui", {}).get("target", {}).get("visible")
            and _effect_hidden(presentation, "target_effect")
        )

    wait(
        "targeting_account_reconnect_returns_without_target",
        reconnect_has_no_target,
        60,
    )
    mark("leave_and_reconnect")

    set_phase("final_safe_positions")
    web_command("target", x=WEB_SAFE_POSITION[0], z=WEB_SAFE_POSITION[1])
    native_command("target", x=PEER_SAFE_POSITION[0], z=PEER_SAFE_POSITION[1])

    def both_are_safe() -> bool:
        web_point = authoritative_xz(web(), web_id)
        native_point = authoritative_xz(desktop(), native_id)
        return (
            web_point is not None
            and native_point is not None
            and math.dist(web_point, WEB_SAFE_POSITION) < 0.5
            and math.dist(native_point, PEER_SAFE_POSITION) < 0.5
        )

    wait(
        "targeting_returns_both_clients_to_safe_positions",
        both_are_safe,
        15,
    )
    web_command("stop")
    native_command("stop")
    page.screenshot(path=str(output / "targeting-final.png"))
    evidence["final_web"] = summary(web())
    evidence["final_native"] = summary(desktop())
    return {
        "target_id": target_id,
        "tested_lives": [life - 1, life],
        "timings_seconds": timings,
        "evidence": evidence,
        "limits": [
            "local protocol-8 exported Web/Linux clients against normal one-dog Yongan",
            "native pointer and Space use the fixed test-probe InputEvent allowlist",
            "fixture approach waits for the server Wild Dog to settle at home before one ordinary move intent; it is not client auto-chase evidence",
            "dual-target far-lock/no-fallback remains covered by the separate server regression",
            "one ordinary Wild Dog kill; this does not execute the five-kill progression branch",
        ],
    }
