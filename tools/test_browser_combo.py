"""Exported-client checks for the server-timed two-step Sword+0 combo."""

from __future__ import annotations

import math
import time

from browser_snapshot import POSITION_VALID, subscribed_player_position

DOG_MAX_HEALTH = 100
DOG_RESPAWN_TIMEOUT_SECONDS = 16
DOG_HOME = [675.0, 575.0]
WEB_SAFE_POSITION = [657.0, 575.0]
NATIVE_SAFE_POSITION = [650.0, 575.0]
COMBO_1 = "actor.player.warrior-male.onehand.combo_1"
COMBO_2 = "actor.player.warrior-male.onehand.combo_2"
COMBO_1_PRE_US = 167_094
COMBO_1_DIRECT_US = 533_333
COMBO_1_DURATION_US = 1_000_000
FOLLOWUP_AFTER_FIRST_ACK_SECONDS = 0.2
TIMING_POLL_SECONDS = 0.01
PRE_FOLLOWUP_READ_GUARD_SECONDS = 0.08


def _monster(snapshot: dict) -> dict:
    rows = snapshot.get("monsters", [])
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


def _action_summary(snapshot: dict, identity: str) -> dict:
    row = _player(snapshot, identity)
    actor = _actor(snapshot, identity)
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
                "z",
            )
        },
        "presentation": {
            key: actor.get(key)
            for key in ("action_id", "attack_sequence", "sequence", "animation_position")
        },
        "monster": {
            key: _monster(snapshot).get(key)
            for key in ("id", "life_sequence", "health", "max_health", "activity", "x", "z")
        },
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

    def action_matches(snapshot: dict, owner: str, action_id: str, sequence: int) -> bool:
        row = _player(snapshot, owner)
        actor = _actor(snapshot, owner)
        return (
            int(row.get("activity", -1)) == 2
            and row.get("attack_action_id") == action_id
            and int(row.get("attack_sequence", -1)) == sequence
            and int(row.get("action_started_at_us", 0)) > 0
            and int(row.get("action_ends_at_us", 0)) > int(row.get("action_started_at_us", 0))
            and actor.get("action_id") == action_id
            and int(actor.get("attack_sequence", -1)) == sequence
        )

    def collect_step_one(
        side: str,
        owner: str,
        peer_read,
        sequence: int,
        observed: dict,
    ) -> bool:
        read = web if side == "web" else desktop
        local_state = read()
        peer_state = peer_read()
        observed_at = round(time.monotonic() - started, 3)
        if "local" not in observed and action_matches(local_state, owner, COMBO_1, sequence):
            observed["local"] = _action_summary(local_state, owner)
            observed["local_observed_elapsed_seconds"] = observed_at
        if "peer" not in observed and action_matches(peer_state, owner, COMBO_1, sequence):
            observed["peer"] = _action_summary(peer_state, owner)
            observed["peer_observed_elapsed_seconds"] = observed_at
        return "local" in observed and "peer" in observed

    def wait_for_step_one(
        label: str,
        side: str,
        owner: str,
        peer_read,
        sequence: int,
        timing: dict,
        first_ack_observed_at: float,
        observed: dict,
    ) -> dict:

        wait(
            label,
            lambda: collect_step_one(side, owner, peer_read, sequence, observed),
            3,
            TIMING_POLL_SECONDS,
        )
        observed_at = time.monotonic()
        timing["both_step_1_observed_elapsed_seconds"] = round(observed_at - started, 3)
        timing["step_1_observation_after_first_ack_seconds"] = round(
            observed_at - first_ack_observed_at, 3
        )
        return observed

    def assert_step_one_matches_ack(observed: dict, public_action: dict) -> None:
        for side_name in ("local", "peer"):
            player = observed[side_name]["player"]
            assert player.get("attack_action_id") == public_action.get("attack_action_id")
            assert int(player.get("attack_sequence", -1)) == int(
                public_action.get("attack_sequence", -2)
            )
            assert int(player.get("action_started_at_us", 0)) == int(
                public_action.get("action_started_at_us", -1)
            )
            assert int(player.get("action_ends_at_us", 0)) == int(
                public_action.get("action_ends_at_us", -1)
            )

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

    def wait_for_ack(side: str, after: int, succeeded: bool) -> dict:
        found: dict = {}

        def ready() -> bool:
            nonlocal found
            ack = last_attack_ack(side)
            sequence = int(ack.get("sequence", 0))
            if sequence <= after:
                return False
            if sequence != after + 1:
                raise AssertionError("Attack ACK sequence skipped the expected reducer completion")
            found = ack.copy()
            if bool(ack.get("succeeded")) is not succeeded:
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
                raise AssertionError("Target ACK sequence skipped the expected reducer completion")
            found = ack.copy()
            if not bool(ack.get("succeeded")):
                raise AssertionError("The exact next target renewal ACK was rejected")
            if not _intent_matches(ack.get("combat_target", {}), target_id, life):
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
        state = web() if side == "web" else desktop()
        dog = _monster(state)
        point = _pick(state, target_id, life)
        authoritative = _authoritative_xz(state, owner)
        rendered = _rendered_xz(state, "rendered_actors", "identity", owner)
        rendered_dog = _rendered_xz(state, "rendered_monsters", "row_id", target_id)
        assert (
            int(dog["life_sequence"]) == life
            and int(dog["health"]) > 0
            and point is not None
            and authoritative is not None
            and rendered is not None
            and rendered_dog is not None
            and math.dist(authoritative, rendered) <= 0.05
            and math.dist([float(dog["x"]), float(dog["z"])], rendered_dog) <= 0.05
        ), "Renewal must use the current exact-life rendered pick projection"
        return state, point

    def run_two_hit_chain(side: str, owner: str, peer_read) -> dict:
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
        timing["pre_followup_read_guard_seconds"] = PRE_FOLLOWUP_READ_GUARD_SECONDS
        ack_sequence = int(first_ack["sequence"])
        first_public = first_ack.get("public_action", {})
        assert first_public.get("attack_action_id") == COMBO_1
        assert int(first_public.get("attack_sequence", -1)) == sequence + 1
        if side == "web":
            page.locator("canvas").focus()
        step_1_observation: dict = {}
        pre_followup_samples = 0
        while deadline - time.monotonic() > PRE_FOLLOWUP_READ_GUARD_SECONDS:
            collect_step_one(side, owner, peer_read, sequence + 1, step_1_observation)
            pre_followup_samples += 1
            time.sleep(TIMING_POLL_SECONDS)
        timing["pre_followup_observation_samples"] = pre_followup_samples
        timing["pre_followup_observed_sides"] = [
            name for name in ("local", "peer") if name in step_1_observation
        ]
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
        renew_state, renew_point = current_live_pick(side, owner, target_id, life)
        if side == "web":
            target_ack_sequence = int(last_target_ack(side).get("sequence", 0))
        else:
            target_rows = renew_state.get("select_combat_target_acks", [])
            target_ack = target_rows[-1] if isinstance(target_rows, list) and target_rows else {}
            target_ack_sequence = int(target_ack.get("sequence", 0))
        if side == "web":
            page.mouse.click(*renew_point)
        else:
            native_command("pointer_click", x=renew_point[0], y=renew_point[1])
        renewal_ack = wait_for_target_ack(side, target_ack_sequence, target_id, life)
        timing["renewal_ack_observed_elapsed_seconds"] = round(time.monotonic() - started, 3)
        assert renewal_ack.get("public_action", {}).get("attack_action_id") == COMBO_1, (
            "Same-target renewal must be accepted while the queued first step is still public"
        )
        assert int(renewal_ack.get("public_action", {}).get("attack_sequence", -1)) == sequence + 1
        renewal_receipt_us = int(renewal_ack.get("reducer_timestamp_us", 0))
        assert queue_receipt_us < renewal_receipt_us
        step_1_observation = wait_for_step_one(
            f"combo_{side}_step1_projects_to_both_clients",
            side,
            owner,
            peer_read,
            sequence + 1,
            timing,
            first_ack_observed_at,
            step_1_observation,
        )
        evidence[f"{side}_step_1_observation"] = step_1_observation
        assert_step_one_matches_ack(step_1_observation, first_public)
        first = step_1_observation["local"]["player"].copy()
        wait(
            f"combo_{side}_first_hit_is_exactly_35_on_both_clients",
            lambda: (
                int(_monster(read())["health"]) == before_health - 35
                and int(_monster(peer_read())["health"]) == before_health - 35
            ),
            4,
        )
        wait(
            f"combo_{side}_step2_projects_to_both_clients",
            lambda: (
                action_matches(read(), owner, COMBO_2, sequence + 2)
                and action_matches(peer_read(), owner, COMBO_2, sequence + 2)
            ),
            3,
            TIMING_POLL_SECONDS,
        )
        second_state = read()
        second = _player(second_state, owner).copy()
        transition_us = int(second["action_started_at_us"]) - int(first["action_started_at_us"])
        assert COMBO_1_DIRECT_US < transition_us < COMBO_1_DURATION_US
        assert renewal_receipt_us < int(second["action_started_at_us"]), (
            "Accepted same-target renewal must precede the queued server transition"
        )
        wait(
            f"combo_{side}_second_hit_is_exactly_35_on_both_clients",
            lambda: (
                int(_monster(read())["health"]) == before_health - 70
                and int(_monster(peer_read())["health"]) == before_health - 70
            ),
            4,
        )
        return {
            "side": side,
            "first_ack": first_ack,
            "queue_ack": queued_ack,
            "renewal_ack": renewal_ack,
            "combo_1": step_1_observation["local"],
            "combo_2": _action_summary(second_state, owner),
            "transition_after_combo_1_us": transition_us,
            "queue_receipt_after_combo_1_us": queue_elapsed_us,
            "health": [before_health, before_health - 35, before_health - 70],
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
        timing["pre_followup_read_guard_seconds"] = PRE_FOLLOWUP_READ_GUARD_SECONDS
        ack_sequence = int(first_ack["sequence"])
        first_public = first_ack.get("public_action", {})
        assert first_public.get("attack_action_id") == COMBO_1
        assert int(first_public.get("attack_sequence", -1)) == sequence + 1
        page.locator("canvas").focus()
        step_1_observation: dict = {}
        pre_followup_samples = 0
        while deadline - time.monotonic() > PRE_FOLLOWUP_READ_GUARD_SECONDS:
            collect_step_one("web", web_id, desktop, sequence + 1, step_1_observation)
            pre_followup_samples += 1
            time.sleep(TIMING_POLL_SECONDS)
        timing["pre_followup_observation_samples"] = pre_followup_samples
        timing["pre_followup_observed_sides"] = [
            name for name in ("local", "peer") if name in step_1_observation
        ]
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
        step_1_observation = wait_for_step_one(
            f"combo_{label}_step1_projects_to_both_clients_after_queue_receipt",
            "web",
            web_id,
            desktop,
            sequence + 1,
            timing,
            first_ack_observed_at,
            step_1_observation,
        )
        evidence[f"{label}_step_1_observation"] = step_1_observation
        assert_step_one_matches_ack(step_1_observation, first_public)
        mutate(sequence + 1)
        saw_combo_2 = False
        deadline = time.monotonic() + 1.4
        while time.monotonic() < deadline:
            for state in (web(), desktop()):
                row = _player(state, web_id)
                if (
                    row.get("attack_action_id") == COMBO_2
                    and int(row.get("attack_sequence", -1)) > sequence + 1
                ):
                    saw_combo_2 = True
            time.sleep(0.08)
        assert not saw_combo_2, f"Accepted {label} cancellation must prevent combo_2"
        after_health = before_health - 35
        assert int(_monster(web())["health"]) == int(_monster(desktop())["health"]) == after_health
        return {
            "queue_ack": ack,
            "queue_receipt_after_combo_1_us": queue_elapsed_us,
            "starting_sequence": sequence,
            "final": _action_summary(web(), web_id),
            "health": [before_health, after_health],
        }

    set_phase("equip_browser")
    equip("web", web_id)
    move_near("web", web_id)
    dog = _monster(web())
    target_id, life = int(dog["id"]), int(dog["life_sequence"])
    select("web", web_id, target_id, life)
    set_phase("browser_two_hit_chain")
    evidence["browser_chain"] = run_two_hit_chain("web", web_id, desktop)
    page.screenshot(path=str(output / "combo-browser-step2.png"))
    life = finish_life("web", web_id, desktop)

    set_phase("equip_native")
    equip("native", native_id)
    move_near("native", native_id)
    native_state = desktop()
    dog = _monster(native_state)
    assert int(dog["life_sequence"]) == life
    select("native", native_id, target_id, life)
    set_phase("native_two_hit_chain")
    evidence["native_chain"] = run_two_hit_chain("native", native_id, web)
    capture_path = output / "desktop.png"
    if capture_path.exists():
        capture_path.unlink()
    native_command("capture")
    wait("combo_native_step2_capture_saved", capture_path.is_file)
    capture_path.replace(output / "combo-native-step2.png")
    life = finish_life("native", native_id, web)
    unequip("native", native_id)

    set_phase("browser_cancellation_setup")
    move_near("web", web_id)
    select("web", web_id, target_id, life)
    assert _intent_matches(web().get("combat_target", {}), target_id, life)
    assert int(_monster(web())["health"]) == DOG_MAX_HEALTH

    def held_and_released_wasd(expected_sequence: int) -> None:
        before_packets = int(web().get("tx_messages", 0))
        before_errors = len(web().get("errors", []))
        before_position = _authoritative_xz(web(), web_id)
        assert before_position is not None
        page.locator("canvas").focus()
        page.keyboard.down("w")
        try:
            wait(
                "combo_held_WASD_sends_movement_after_queue_ack",
                lambda: int(web().get("tx_messages", 0)) > before_packets,
                2,
            )

            def moves_after_attack_window() -> bool:
                state = web()
                row = _player(state, web_id)
                if (
                    row.get("attack_action_id") == COMBO_2
                    and int(row.get("attack_sequence", -1)) > expected_sequence
                ):
                    raise AssertionError("Held WASD did not cancel the accepted queued link")
                position = _authoritative_xz(state, web_id)
                return position is not None and math.dist(position, before_position) > 0.1

            wait(
                "combo_held_WASD_moves_only_after_current_attack_window",
                moves_after_attack_window,
                3,
            )
        finally:
            page.keyboard.up("w")
        wait(
            "combo_released_WASD_stop_is_accepted",
            lambda: (
                int(web().get("activity", -1)) == 0
                and len(web().get("errors", [])) == before_errors
            ),
            3,
        )

    set_phase("cancel_held_released_wasd")
    evidence["held_released_wasd_cancel"] = run_cancel("held_released_WASD", held_and_released_wasd)
    assert _intent_matches(web().get("combat_target", {}), target_id, life)
    move_safe("web", web_id)
    move_near("web", web_id)
    select("web", web_id, target_id, life)

    ground_origin: list[float] = []

    def ground_click(_expected_sequence: int) -> None:
        nonlocal ground_origin
        state = web()
        ground_origin = _authoritative_xz(state, web_id) or []
        assert ground_origin
        ground = state.get("ground_pick", {})
        point = ground.get("screen", [])
        assert ground.get("available") is True and len(point) == 2
        page.mouse.click(float(point[0]), float(point[1]))

    set_phase("cancel_ground_click")
    evidence["ground_cancel"] = run_cancel("ground_click", ground_click)
    assert _intent_matches(web().get("combat_target", {}), target_id, life)
    wait(
        "combo_ground_click_moves_only_after_current_attack_window",
        lambda: (
            (position := _authoritative_xz(web(), web_id)) is not None
            and math.dist(position, ground_origin) > 0.1
        ),
        2,
    )
    move_near("web", web_id)
    life = finish_life("web", web_id, desktop)
    move_near("web", web_id)
    select("web", web_id, target_id, life)

    def clear_target(_expected_sequence: int) -> None:
        state = web()
        close = state.get("ui", {}).get("target", {}).get("close_center", [])
        assert len(close) == 2
        page.mouse.click(float(close[0]), float(close[1]))
        wait(
            "combo_target_clear_is_accepted_after_queue_ack", lambda: not web().get("combat_target")
        )

    set_phase("cancel_target_clear")
    evidence["clear_cancel"] = run_cancel("target_clear", clear_target)
    assert not web().get("combat_target")

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
        "limits": [
            "follow-up reducer receipt timestamps are checked inside the source pre/direct window; exact endpoint equality remains server-test evidence",
            "queue acceptance is the exact next typed reducer ACK while combo_1 remains public",
            "the client never projects queue state or starts combo_2 optimistically",
            "fixture approach waits for the server Wild Dog to settle at home before one ordinary move intent; it is not client auto-chase evidence",
            "target-clear cancellation deliberately leaves the disposable dog at 65 HP; the following actor smoke is presentation-only with both actors out of range",
            "one source-derived two-step Sword+0 chain; no later steps, root motion, area attacks, or PvP",
        ],
    }
