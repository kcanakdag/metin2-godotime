"""Exported canvas checks for owner progression, Status, and private commands."""

from __future__ import annotations

import math
import time

from browser_snapshot import (
    POSITION_VALID,
    authoritative_position_distance,
    subscribed_player_position,
)

DOG_MAX_HEALTH = 100
DOG_RESPAWN_US = 12_000_000
DOG_RESPAWN_TIMEOUT_SECONDS = 16
DOG_ACQUISITION_RANGE = 8.0
DOG_CHASE_HOME_RANGE = 16.0
PLAYER_NORMAL_ATTACK_ID = "actor.player.warrior-male.general.normal_attack.v1"
MONSTER_HOME = [675.0, 575.0]
SAFE_POSITION = [657.0, 575.0]
PEER_SAFE_POSITION = [650.0, 575.0]


def _actor_position(snapshot: dict, identity: str) -> list[float] | None:
    return next(
        (
            actor.get("position")
            for actor in snapshot.get("rendered_actors", [])
            if actor.get("identity") == identity
        ),
        None,
    )


def _selected_progression(snapshot: dict, identity: str) -> dict:
    return next(
        (row for row in snapshot.get("progression", []) if row.get("character_id") == identity),
        {},
    )


def _feedback_ids(snapshot: dict) -> set[int]:
    return {int(row["id"]) for row in snapshot.get("command_feedback", [])}


def _public_message_count(snapshot: dict) -> int:
    return int(snapshot.get("ui", {}).get("chat", {}).get("message_count", 0))


def _player(snapshot: dict, identity: str) -> dict:
    return next(
        (row for row in snapshot.get("player_rows", []) if row.get("identity") == identity),
        {},
    )


def _monster(snapshot: dict) -> dict:
    rows = snapshot.get("monsters", [])
    assert len(rows) == 1, "Progression combat requires exactly one subscribed Wild Dog"
    row = rows[0]
    assert row.get("definition_vnum") == 101 and row.get("name") == "Wild Dog"
    return row


def _inventory_potion_count(snapshot: dict) -> int:
    return sum(int(row["count"]) for row in snapshot.get("inventory", []) if row["vnum"] == 27001)


def _xz_distance(position: list[float], row: dict) -> float:
    return math.dist([position[0], position[2]], [float(row["x"]), float(row["z"])])


def _submit(page, snapshot, wait, text: str) -> None:
    page.keyboard.press("Enter")
    wait("private_command_chat_receives_focus", lambda: snapshot()["ui"]["chat"]["focused"])
    page.keyboard.type(text)
    page.keyboard.press("Enter")
    wait(
        "private_command_chat_releases_focus",
        lambda: not snapshot()["ui"]["chat"]["focused"],
    )


def exercise_progression(
    page,
    web,
    desktop,
    web_command,
    wait,
    web_id: str,
    native_id: str,
    output,
) -> dict:
    """Use visible controls and ordinary command reducers; no privileged control path."""

    def owner_rows_match() -> bool:
        web_rows = web().get("progression", [])
        native_rows = desktop().get("progression", [])
        web_owned = {row["character_id"] for row in web()["account"]["characters"]}
        native_owned = {row["character_id"] for row in desktop()["account"]["characters"]}
        return (
            bool(_selected_progression(web(), web_id))
            and bool(_selected_progression(desktop(), native_id))
            and {row["character_id"] for row in web_rows} == web_owned
            and {row["character_id"] for row in native_rows} == native_owned
            and web_owned.isdisjoint(native_owned)
            and all("account" not in row for row in web_rows + native_rows)
        )

    wait("both_clients_receive_only_owned_progression_rows", owner_rows_match)
    selected = _selected_progression(web(), web_id)
    page.locator("canvas").focus()
    page.keyboard.press("c")
    wait("C_opens_subscribed_character_status", lambda: web()["ui"]["status"]["visible"])

    def status_matches() -> bool:
        state = web()["ui"]["status"]
        taskbar = web()["ui"]["taskbar"]
        roster_values = web()["account"]["character_values"]
        values = state["values"]
        quarter = max(1, selected["next_exp"] // 4) if selected["next_exp"] else 1
        quarters = min(4.0, selected["experience"] / quarter)
        expected_heights = [19.0 * min(1.0, max(0.0, quarters - index)) for index in range(4)]
        actual_heights = [fill["height"] for fill in taskbar["xp_fills"]]
        expected_plus = {
            "st": selected["unspent_stat_points"] > 0 and selected["strength"] < 90,
            "ht": selected["unspent_stat_points"] > 0 and selected["vitality"] < 90,
            "dx": selected["unspent_stat_points"] > 0 and selected["dexterity"] < 90,
            "iq": selected["unspent_stat_points"] > 0 and selected["intelligence"] < 90,
        }
        return (
            state.get("character_id") == web_id
            and roster_values.get("level") == str(selected["level"])
            and roster_values.get("str") == str(selected["strength"])
            and roster_values.get("hth") == str(selected["vitality"])
            and roster_values.get("dex") == str(selected["dexterity"])
            and roster_values.get("int") == str(selected["intelligence"])
            and values.get("level") == str(selected["level"])
            and values.get("experience") == str(selected["experience"])
            and values.get("remaining_exp")
            == str(max(0, selected["next_exp"] - selected["experience"]))
            and values.get("strength") == str(selected["strength"])
            and values.get("vitality") == str(selected["vitality"])
            and values.get("dexterity") == str(selected["dexterity"])
            and values.get("intelligence") == str(selected["intelligence"])
            and values.get("sp") == f"{selected['current_sp']}/{selected['max_sp']}"
            and all(
                math.isclose(actual, expected, abs_tol=0.05)
                for actual, expected in zip(actual_heights, expected_heights, strict=True)
            )
            and state["points_visible"] == (selected["unspent_stat_points"] > 0)
            and all(
                state["plus"][code]["visible"] == expected
                for code, expected in expected_plus.items()
            )
        )

    wait("Status_renders_authoritative_selected_progression", status_matches)
    web_command("stop")
    wait("browser_stops_before_chat_focus_check", lambda: web().get("activity") == 0)

    def both_clients_have_authoritative_rendered_positions() -> bool:
        web_state, native_state = web(), desktop()
        web_own_status, web_own = subscribed_player_position(web_state, web_id)
        web_peer_status, web_peer = subscribed_player_position(web_state, native_id)
        native_own_status, native_own = subscribed_player_position(native_state, native_id)
        native_peer_status, native_peer = subscribed_player_position(native_state, web_id)
        rendered_web_peer = _actor_position(native_state, web_id)
        rendered_native_peer = _actor_position(web_state, native_id)
        positions = (web_own, web_peer, native_own, native_peer)
        return (
            web_own_status
            == web_peer_status
            == native_own_status
            == native_peer_status
            == POSITION_VALID
            and all(position is not None for position in positions)
            and rendered_web_peer is not None
            and rendered_native_peer is not None
            and authoritative_position_distance(web_own, native_peer) < 0.02
            and authoritative_position_distance(web_peer, native_own) < 0.02
            and authoritative_position_distance(rendered_web_peer, web_own) < 0.1
            and authoritative_position_distance(rendered_native_peer, native_own) < 0.1
        )

    wait(
        "both_clients_have_own_peer_authoritative_and_rendered_positions",
        both_clients_have_authoritative_rendered_positions,
    )
    web_state, native_state = web(), desktop()
    own_status, own_start = subscribed_player_position(web_state, web_id)
    peer_status, peer_start = subscribed_player_position(web_state, native_id)
    native_own_status, native_own_start = subscribed_player_position(native_state, native_id)
    native_peer_status, native_peer_start = subscribed_player_position(native_state, web_id)
    assert own_status == peer_status == native_own_status == native_peer_status == POSITION_VALID
    assert all(
        position is not None
        for position in (own_start, peer_start, native_own_start, native_peer_start)
    )
    remote_start = _actor_position(native_state, web_id)
    rendered_native_start = _actor_position(web_state, native_id)
    assert remote_start is not None and rendered_native_start is not None
    chat_before = web()["ui"]["chat"]
    public_before = chat_before["message_count"]
    native_public_before = _public_message_count(desktop())
    local_before = chat_before["local_info_count"]
    web_feedback_before = _feedback_ids(web())
    native_feedback_before = _feedback_ids(desktop())
    page.keyboard.press("Enter")
    wait("unknown_slash_chat_receives_focus", lambda: web()["ui"]["chat"]["focused"])
    page.keyboard.type("/wasd")
    time.sleep(0.35)
    remote_after_typing = _actor_position(desktop(), web_id)
    assert remote_after_typing is not None
    assert math.dist(remote_start, remote_after_typing) < 0.1, (
        "Typing WASD in the focused chat moved the authoritative avatar"
    )
    own_status, own_after = subscribed_player_position(web(), web_id)
    peer_status, peer_after = subscribed_player_position(web(), native_id)
    native_own_status, native_own_after = subscribed_player_position(desktop(), native_id)
    native_peer_status, native_peer_after = subscribed_player_position(desktop(), web_id)
    assert own_status == peer_status == native_own_status == native_peer_status == POSITION_VALID
    assert all(
        position is not None
        for position in (own_after, peer_after, native_own_after, native_peer_after)
    )
    assert authoritative_position_distance(own_start, own_after) < 0.1, (
        "Typing WASD in focused chat moved the subscribed own player row"
    )
    assert authoritative_position_distance(peer_start, peer_after) < 0.1, (
        "Typing WASD in focused chat moved the subscribed peer player row"
    )
    assert authoritative_position_distance(native_own_start, native_own_after) < 0.1, (
        "Typing WASD in focused chat moved the native subscribed own player row"
    )
    assert authoritative_position_distance(native_peer_start, native_peer_after) < 0.1, (
        "Typing WASD in focused chat moved the native subscribed peer player row"
    )
    rendered_native_after = _actor_position(web(), native_id)
    assert rendered_native_after is not None
    assert authoritative_position_distance(rendered_native_start, rendered_native_after) < 0.1, (
        "Typing WASD in focused chat moved the rendered native peer"
    )
    page.keyboard.press("Enter")
    wait(
        "unknown_slash_stays_private_local_Info",
        lambda: web()["ui"]["chat"]["local_info_count"] == local_before + 1,
    )
    assert web()["ui"]["chat"]["message_count"] == public_before
    assert _public_message_count(desktop()) == native_public_before
    assert _feedback_ids(web()) == web_feedback_before
    _submit(page, web, wait, "/help")
    wait(
        "help_returns_private_server_feedback",
        lambda: any(
            row["id"] not in web_feedback_before
            and row["severity"] == "info"
            and row["message"].startswith("Commands: /help")
            for row in web().get("command_feedback", [])
        ),
    )
    wait(
        "help_feedback_is_visible_in_local_Info",
        lambda: any(
            line.startswith("Info : Commands: /help")
            for line in web()["ui"]["chat"]["feedback_lines"]
        ),
    )
    help_feedback = _feedback_ids(web())
    assert _feedback_ids(desktop()) == native_feedback_before, (
        "Private web feedback leaked to the other authenticated account"
    )
    assert web()["ui"]["chat"]["message_count"] == public_before
    assert _public_message_count(desktop()) == native_public_before
    baseline = _selected_progression(web(), web_id).copy()
    # The server's frozen command policy permits one request per second.
    time.sleep(1.1)
    _submit(page, web, wait, "/xp 1")
    wait(
        "default_deny_xp_returns_private_error",
        lambda: any(
            row["id"] not in help_feedback
            and row["severity"] == "error"
            and row["message"] == "This account lacks progression-admin access."
            for row in web().get("command_feedback", [])
        ),
    )
    wait(
        "default_deny_is_visible_in_local_Info",
        lambda: (
            "Info : This account lacks progression-admin access."
            in web()["ui"]["chat"]["feedback_lines"]
        ),
    )
    assert _selected_progression(web(), web_id) == baseline, (
        "Denied private XP command mutated subscribed progression"
    )
    assert _feedback_ids(desktop()) == native_feedback_before, (
        "Private command denial leaked to the other authenticated account"
    )
    assert web()["ui"]["chat"]["message_count"] == public_before
    assert _public_message_count(desktop()) == native_public_before
    wait("denied_XP_preserves_Status_values", status_matches)
    page.screenshot(path=str(output / "progression-status-feedback.png"))
    page.keyboard.press("c")
    wait("C_closes_character_status", lambda: not web()["ui"]["status"]["visible"])
    return {
        "selected_progression": _selected_progression(web(), web_id),
        "feedback": web().get("command_feedback", []),
        "status": web()["ui"]["status"],
        "peer_progression": _selected_progression(desktop(), native_id),
    }


def exercise_progression_combat(
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
    """Kill five production Wild Dog lives and spend the earned VIT point through the UI."""

    combat_started = time.monotonic()
    phase = "initial"
    trace: list[dict] = []
    last_fingerprints: dict[str, tuple] = {}
    latest_summaries: dict[str, dict] = {}
    diagnostics.clear()
    diagnostics["trace"] = trace

    def summarize(side: str, snapshot: dict) -> dict:
        rows = snapshot.get("monsters")
        monsters = rows if isinstance(rows, list) else []
        rendered_rows = snapshot.get("rendered_monsters")
        identity = web_id if side == "web" else native_id
        player = _player(snapshot, identity)
        return {
            "elapsed_seconds": round(time.monotonic() - combat_started, 3),
            "phase": phase,
            "side": side,
            "connection_state": snapshot.get("connection_state"),
            "state_message": snapshot.get("state_message"),
            "identity": snapshot.get("identity"),
            "rx_messages": snapshot.get("rx_messages"),
            "snapshot_age_ms": snapshot.get("snapshot_age_ms"),
            "monster_count": len(monsters) if isinstance(rows, list) else None,
            "rendered_monster_count": (
                len(rendered_rows) if isinstance(rendered_rows, list) else None
            ),
            "monsters": [
                {
                    "id": row.get("id"),
                    "life_sequence": row.get("life_sequence"),
                    "health": row.get("health"),
                    "max_health": row.get("max_health"),
                    "activity": row.get("activity"),
                    "respawn_at_us": row.get("respawn_at_us"),
                }
                for row in monsters
                if isinstance(row, dict)
            ],
            "player": {
                "health": player.get("health"),
                "max_health": player.get("max_health"),
                "activity": player.get("activity"),
                "life_sequence": player.get("life_sequence"),
                "x": player.get("x"),
                "z": player.get("z"),
            },
        }

    def observe(side: str, snapshot: dict) -> None:
        summary = summarize(side, snapshot)
        fingerprint = (
            summary["phase"],
            summary["connection_state"],
            summary["state_message"],
            summary["identity"],
            summary["rx_messages"],
            summary["monster_count"],
            summary["rendered_monster_count"],
            tuple(
                (
                    row["id"],
                    row["life_sequence"],
                    row["health"],
                    row["activity"],
                    row["respawn_at_us"],
                )
                for row in summary["monsters"]
            ),
            tuple(summary["player"].values()),
        )
        latest_summaries[side] = summary
        if fingerprint == last_fingerprints.get(side):
            return
        last_fingerprints[side] = fingerprint
        trace.append(summary)
        del trace[:-128]

    read_web, read_desktop = web, desktop

    def web() -> dict:
        snapshot = read_web()
        observe("web", snapshot)
        return snapshot

    def desktop() -> dict:
        snapshot = read_desktop()
        observe("native", snapshot)
        return snapshot

    def monster(snapshot: dict) -> dict:
        rows = snapshot.get("monsters")
        side = "web" if snapshot.get("identity") == web_id else "native"
        if not isinstance(rows, list) or len(rows) != 1:
            other_side = "native" if side == "web" else "web"
            try:
                other_snapshot = read_desktop() if other_side == "native" else read_web()
                observe(other_side, other_snapshot)
            except Exception as error:  # Preserve the primary mismatching snapshot.
                diagnostics["other_side_read_error"] = str(error)
            diagnostics["mismatch"] = {
                "elapsed_seconds": round(time.monotonic() - combat_started, 3),
                "phase": phase,
                "side": side,
                "snapshot": snapshot,
                "other_side_latest": latest_summaries.get(other_side, {}),
            }
            count = len(rows) if isinstance(rows, list) else "non-list"
            raise AssertionError(
                f"Progression combat requires exactly one subscribed Wild Dog; "
                f"{side} snapshot has {count}"
            )
        return _monster(snapshot)

    baseline = _selected_progression(web(), web_id).copy()
    peer_baseline = _selected_progression(desktop(), native_id).copy()
    expected_initial = {
        "level": 1,
        "experience": 0,
        "next_exp": 300,
        "level_step": 0,
        "unspent_stat_points": 0,
        "strength": 6,
        "vitality": 4,
        "dexterity": 3,
        "intelligence": 3,
        "current_sp": 260,
        "max_sp": 260,
    }
    assert baseline == {"character_id": web_id, **expected_initial}
    assert peer_baseline == {"character_id": native_id, **expected_initial}
    assert not _selected_progression(web(), native_id)
    assert not _selected_progression(desktop(), web_id)

    initial_player = _player(web(), web_id).copy()
    initial_peer = _player(desktop(), native_id).copy()
    assert int(initial_player["health"]) == int(initial_player["max_health"]) == 760
    assert int(initial_peer["health"]) == int(initial_peer["max_health"]) == 760
    initial_potions = _inventory_potion_count(web())
    assert initial_potions == 5
    assert len(web().get("inventory", [])) == 2
    assert not next(row for row in web()["inventory"] if row["vnum"] == 10)["equipped"]
    initial_gold = int(initial_player["gold"])
    initial_drop_ids = {int(row["id"]) for row in web().get("item_drops", [])}

    phase = "park_native"
    native_command("target", x=PEER_SAFE_POSITION[0], z=PEER_SAFE_POSITION[1])

    def native_reaches_safe_position() -> bool:
        native_status, native_position = subscribed_player_position(desktop(), native_id)
        peer_status, peer_position = subscribed_player_position(web(), native_id)
        return (
            native_status == peer_status == POSITION_VALID
            and native_position is not None
            and peer_position is not None
            and math.dist([native_position[0], native_position[2]], PEER_SAFE_POSITION) < 0.5
            and authoritative_position_distance(native_position, peer_position) < 0.1
        )

    wait("progression_combat_parks_native_safely", native_reaches_safe_position, 10)
    native_command("stop")
    wait(
        "progression_combat_native_stops_outside_dog_chase_range",
        lambda: desktop().get("activity") == 0,
    )
    peer_status, peer_position = subscribed_player_position(desktop(), native_id)
    assert peer_status == POSITION_VALID and peer_position is not None

    phase = "initial_fresh_life"

    def fresh_dog_on_both_clients() -> bool:
        web_dog, native_dog = monster(web()), monster(desktop())
        return (
            int(web_dog["health"])
            == int(web_dog["max_health"])
            == int(native_dog["health"])
            == int(native_dog["max_health"])
            == DOG_MAX_HEALTH
            and int(web_dog["respawn_at_us"]) == int(native_dog["respawn_at_us"]) == 0
            and int(web_dog["life_sequence"]) == int(native_dog["life_sequence"])
        )

    wait(
        "progression_combat_starts_with_fresh_Wild_Dog_life",
        fresh_dog_on_both_clients,
        DOG_RESPAWN_TIMEOUT_SECONDS,
    )
    dog = monster(web())
    assert _xz_distance(peer_position, dog) > DOG_CHASE_HOME_RANGE
    first_life = int(dog["life_sequence"])
    killed_lives: list[int] = []
    seen_drop_ids: set[int] = set()
    delayed_hit_seconds: list[float] = []
    respawn_seconds: list[float] = []
    pre_quarter_health = 0
    death_observed_at = 0.0

    for kill_index in range(1, 6):
        phase = f"life_{kill_index}_approach"
        dog = monster(web())
        expected_life = first_life + kill_index - 1
        assert int(dog["life_sequence"]) == expected_life
        assert dog["health"] == dog["max_health"] == DOG_MAX_HEALTH
        assert dog["respawn_at_us"] == 0
        web_command("target", x=dog["x"], z=dog["z"])

        def in_reach_of_current_life(life: int = expected_life) -> bool:
            state = web()
            current = monster(state)
            status, position = subscribed_player_position(state, web_id)
            return (
                status == POSITION_VALID
                and position is not None
                and int(current["life_sequence"]) == life
                and int(current["health"]) > 0
                and _xz_distance(position, current) < 2.6
            )

        wait(
            f"progression_combat_life_{kill_index}_reaches_Wild_Dog",
            in_reach_of_current_life,
            15,
        )
        web_command("stop")
        wait(
            f"progression_combat_life_{kill_index}_stops_in_reach",
            lambda: web().get("activity") == 0,
        )
        if kill_index == 5:
            pre_quarter_health = int(_player(web(), web_id)["health"])
            assert 0 < pre_quarter_health < int(_player(web(), web_id)["max_health"]), (
                "The first four ordinary dog lives must damage the player before the quarter"
            )

        for hit_index in range(1, 5):
            phase = f"life_{kill_index}_hit_{hit_index}"
            before = web()
            current = monster(before)
            assert int(current["life_sequence"]) == expected_life
            assert int(current["health"]) == DOG_MAX_HEALTH - (hit_index - 1) * 25
            attack_sequence = int(_player(before, web_id)["attack_sequence"])
            page.locator("canvas").focus()
            attack_sent_at = time.monotonic()
            page.keyboard.press("Space")

            def hit_resolved(
                life: int = expected_life,
                index: int = hit_index,
                sequence: int = attack_sequence,
            ) -> bool:
                state = web()
                current_dog = monster(state)
                expected_health = max(0, DOG_MAX_HEALTH - index * 25)
                return (
                    int(current_dog["life_sequence"]) == life
                    and int(current_dog["health"]) == expected_health
                    and int(_player(state, web_id)["attack_sequence"]) == sequence + 1
                    and _player(state, web_id)["attack_action_id"] == PLAYER_NORMAL_ATTACK_ID
                )

            wait(
                f"progression_combat_life_{kill_index}_hit_{hit_index}_resolves",
                hit_resolved,
                3,
            )
            hit_elapsed = time.monotonic() - attack_sent_at
            assert 0.25 <= hit_elapsed < 3.0, (
                "Wild Dog damage resolved outside the normal hit window"
            )
            delayed_hit_seconds.append(hit_elapsed)
            if hit_index < 4:
                time.sleep(1.0)

        phase = f"life_{kill_index}_death"

        def dead_on_both_clients(life: int = expected_life) -> bool:
            web_dog = monster(web())
            native_dog = monster(desktop())
            return (
                int(web_dog["life_sequence"]) == life
                and int(web_dog["health"]) == 0
                and int(native_dog["life_sequence"]) == life
                and int(native_dog["health"]) == 0
            )

        wait(
            f"progression_combat_life_{kill_index}_dies_on_both_clients",
            dead_on_both_clients,
        )
        death_observed_at = time.monotonic()
        dead_dog = monster(web())
        assert (
            int(dead_dog["respawn_at_us"]) - int(dead_dog["action_started_at_us"]) == DOG_RESPAWN_US
        )
        killed_lives.append(expected_life)
        phase = f"life_{kill_index}_rewards"
        expected_experience = kill_index * 15
        wait(
            f"progression_combat_kill_{kill_index}_awards_exactly_15_XP",
            lambda experience=expected_experience: (
                int(_selected_progression(web(), web_id).get("experience", -1)) == experience
            ),
        )
        current_progression = _selected_progression(web(), web_id)
        assert int(current_progression["level"]) == 1
        assert int(current_progression["level_step"]) == (1 if kill_index == 5 else 0)
        assert int(current_progression["unspent_stat_points"]) == (1 if kill_index == 5 else 0)
        assert _selected_progression(desktop(), native_id) == peer_baseline
        assert not _selected_progression(desktop(), web_id)
        assert int(_player(desktop(), native_id)["health"]) == int(initial_peer["health"])
        peer_now_status, peer_now = subscribed_player_position(desktop(), native_id)
        assert peer_now_status == POSITION_VALID and peer_now is not None
        assert authoritative_position_distance(peer_position, peer_now) < 0.1
        expected_potions = initial_potions + (2 if kill_index == 5 else 0)
        wait(
            f"progression_combat_kill_{kill_index}_preserves_exact_inventory_potions",
            lambda count=expected_potions: _inventory_potion_count(web()) == count,
        )
        assert int(_player(web(), web_id)["gold"]) == initial_gold

        def current_life_drop_ids() -> set[int]:
            return {
                int(row["id"])
                for row in web().get("item_drops", [])
                if int(row["id"]) not in initial_drop_ids | seen_drop_ids
                and row.get("owner") == web_id
            }

        wait(
            f"progression_combat_kill_{kill_index}_leaves_uncollected_death_potion",
            lambda: len(current_life_drop_ids()) == 1,
        )
        unseen_drop_ids = current_life_drop_ids()
        assert len(unseen_drop_ids) == 1, "The current Wild Dog ground drop is missing"
        seen_drop_ids.update(unseen_drop_ids)

        if kill_index < 5:
            phase = f"life_{kill_index}_respawn"

            def respawned_on_both_clients(life: int = expected_life + 1) -> bool:
                web_dog = monster(web())
                native_dog = monster(desktop())
                return (
                    int(web_dog["life_sequence"]) == life
                    and int(web_dog["health"]) == DOG_MAX_HEALTH
                    and int(web_dog["respawn_at_us"]) == 0
                    and int(native_dog["life_sequence"]) == life
                    and int(native_dog["health"]) == DOG_MAX_HEALTH
                )

            wait(
                f"progression_combat_life_{kill_index}_production_respawn",
                respawned_on_both_clients,
                DOG_RESPAWN_TIMEOUT_SECONDS,
            )
            respawn_elapsed = time.monotonic() - death_observed_at
            assert 11.0 <= respawn_elapsed < DOG_RESPAWN_TIMEOUT_SECONDS
            respawn_seconds.append(respawn_elapsed)

    assert len(killed_lives) == len(set(killed_lives)) == 5
    assert len(seen_drop_ids) == 5
    post_quarter = _selected_progression(web(), web_id).copy()
    assert post_quarter["experience"] == 75
    assert post_quarter["level_step"] == 1
    assert post_quarter["unspent_stat_points"] == 1
    assert post_quarter["current_sp"] == post_quarter["max_sp"] == 260
    assert _inventory_potion_count(web()) == initial_potions + 2
    assert int(_player(web(), web_id)["health"]) == int(_player(web(), web_id)["max_health"]) == 760
    assert 0 < pre_quarter_health < 760

    final_fresh_life = first_life + 5
    phase = "final_fresh_respawn"

    def final_dog_respawned() -> bool:
        web_dog, native_dog = monster(web()), monster(desktop())
        return (
            int(web_dog["life_sequence"]) == int(native_dog["life_sequence"]) == final_fresh_life
            and int(web_dog["health"]) == int(native_dog["health"]) == DOG_MAX_HEALTH
            and int(web_dog["respawn_at_us"]) == int(native_dog["respawn_at_us"]) == 0
        )

    wait(
        "progression_combat_final_production_respawn_is_fresh",
        final_dog_respawned,
        DOG_RESPAWN_TIMEOUT_SECONDS,
    )
    final_respawn_elapsed = time.monotonic() - death_observed_at
    assert 11.0 <= final_respawn_elapsed < DOG_RESPAWN_TIMEOUT_SECONDS
    respawn_seconds.append(final_respawn_elapsed)
    phase = "take_post_quarter_damage"
    wait(
        "progression_combat_takes_damage_before_VIT_allocation",
        lambda: (
            int(monster(web())["life_sequence"]) == final_fresh_life
            and int(monster(web())["health"]) == DOG_MAX_HEALTH
            and 0 < int(_player(web(), web_id)["health"]) < 760
        ),
        6,
    )

    # Leave the fresh dog alive and retreat beyond acquisition before measuring
    # current HP. Waiting past its pending hit window removes the allocation race.
    phase = "retreat_after_damage"
    web_command("target", x=SAFE_POSITION[0], z=SAFE_POSITION[1])

    def retreated_from_live_dog() -> bool:
        state = web()
        position_status, position = subscribed_player_position(state, web_id)
        return (
            int(monster(state)["life_sequence"]) == final_fresh_life
            and int(monster(state)["health"]) == DOG_MAX_HEALTH
            and position_status == POSITION_VALID
            and position is not None
            and math.dist([position[0], position[2]], SAFE_POSITION) < 0.5
            and math.dist([position[0], position[2]], MONSTER_HOME) > DOG_CHASE_HOME_RANGE
            and _xz_distance(position, monster(state)) > DOG_ACQUISITION_RANGE
        )

    wait(
        "progression_combat_retreats_from_live_dog_after_damage",
        retreated_from_live_dog,
        8,
    )
    web_command("stop")
    wait(
        "progression_combat_stops_safely_before_VIT_allocation",
        lambda: web().get("activity") == 0 and retreated_from_live_dog(),
    )
    before_allocation_player = _player(web(), web_id).copy()
    assert 0 < int(before_allocation_player["health"]) < int(before_allocation_player["max_health"])
    time.sleep(0.75)
    wait(
        "progression_combat_partial_health_is_stable_out_of_range",
        lambda: (
            int(_player(web(), web_id)["health"]) == int(before_allocation_player["health"])
            and int(_player(desktop(), web_id)["health"]) == int(before_allocation_player["health"])
            and int(_player(desktop(), native_id)["health"]) == int(initial_peer["health"])
        ),
    )
    phase = "allocate_vitality"
    page.locator("canvas").focus()
    page.keyboard.press("c")
    wait(
        "progression_combat_opens_positive_subscribed_Status",
        lambda: (
            web()["ui"]["status"]["visible"]
            and web()["ui"]["status"]["plus"]["ht"]["visible"]
            and not web()["ui"]["status"]["plus"]["ht"]["disabled"]
        ),
    )
    vitality_button = web()["ui"]["status"]["plus"]["ht"]
    page.mouse.click(*vitality_button["center"])

    def vitality_applied() -> bool:
        state = web()
        row = _selected_progression(state, web_id)
        player = _player(state, web_id)
        return (
            int(row.get("vitality", -1)) == int(post_quarter["vitality"]) + 1
            and int(row.get("unspent_stat_points", -1)) == 0
            and int(player.get("max_health", -1))
            == int(before_allocation_player["max_health"]) + 40
            and int(player.get("health", -1)) == int(before_allocation_player["health"])
            and state["account"]["character_values"].get("hth") == "5"
        )

    wait("progression_combat_VIT_plus_updates_server_state", vitality_applied)

    def positive_status_matches() -> bool:
        state = web()
        row = _selected_progression(state, web_id)
        player = _player(state, web_id)
        status_state = state["ui"]["status"]
        taskbar_state = state["ui"]["taskbar"]
        values = status_state["values"]
        expected_hp_width = 95.0 * int(player["health"]) / int(player["max_health"])
        return (
            status_state.get("character_id") == web_id
            and not status_state.get("loading")
            and values.get("level") == "1"
            and values.get("experience") == "75"
            and values.get("remaining_exp") == "225"
            and values.get("strength") == "6"
            and values.get("vitality") == "5"
            and values.get("dexterity") == "3"
            and values.get("intelligence") == "3"
            and values.get("unspent_stat_points") == "0"
            and values.get("health") == f"{player['health']}/{player['max_health']}"
            and values.get("sp") == "260/260"
            and int(row.get("current_sp", -1)) == int(row.get("max_sp", -2)) == 260
            and not status_state["points_visible"]
            and all(
                not control["visible"] and control["disabled"]
                for control in status_state["plus"].values()
            )
            and taskbar_state.get("xp_tooltip") == "XP: 75 / 300 (25.00%)"
            and [fill["height"] for fill in taskbar_state.get("xp_fills", [])] == [19, 0, 0, 0]
            and math.isclose(
                float(taskbar_state.get("hp_width", -1)), expected_hp_width, abs_tol=0.05
            )
            and math.isclose(float(taskbar_state.get("sp_width", -1)), 95.0, abs_tol=0.05)
        )

    wait(
        "progression_combat_renders_positive_source_Status_and_quarter_orb",
        positive_status_matches,
    )
    final_state = web()
    final_progression = _selected_progression(final_state, web_id)
    final_player = _player(final_state, web_id)
    status = final_state["ui"]["status"]
    taskbar = final_state["ui"]["taskbar"]
    assert status["character_id"] == web_id and not status["loading"]
    assert status["values"]["experience"] == "75"
    assert status["values"]["remaining_exp"] == "225"
    assert status["values"]["level"] == "1"
    assert status["values"]["strength"] == "6"
    assert status["values"]["vitality"] == str(final_progression["vitality"])
    assert status["values"]["dexterity"] == "3"
    assert status["values"]["intelligence"] == "3"
    assert status["values"]["unspent_stat_points"] == "0"
    assert status["values"]["health"] == (
        f"{before_allocation_player['health']}/{final_player['max_health']}"
    )
    assert status["values"]["sp"] == "260/260"
    assert not status["points_visible"]
    assert all(
        not control["visible"] and control["disabled"] for control in status["plus"].values()
    )
    assert taskbar["xp_tooltip"] == "XP: 75 / 300 (25.00%)"
    assert [fill["height"] for fill in taskbar["xp_fills"]] == [19, 0, 0, 0]
    expected_hp_width = 95.0 * int(final_player["health"]) / int(final_player["max_health"])
    assert math.isclose(float(taskbar["hp_width"]), expected_hp_width, abs_tol=0.05)
    assert math.isclose(float(taskbar["sp_width"]), 95.0, abs_tol=0.05)
    assert final_player["health"] == before_allocation_player["health"]
    assert final_progression == {
        **baseline,
        "experience": 75,
        "level_step": 1,
        "unspent_stat_points": 0,
        "vitality": 5,
    }
    assert _inventory_potion_count(final_state) == initial_potions + 2
    assert _selected_progression(desktop(), native_id) == peer_baseline
    assert not _selected_progression(web(), native_id)
    assert not _selected_progression(desktop(), web_id)
    assert _player(desktop(), web_id)["health"] == final_player["health"]
    assert _player(desktop(), web_id)["max_health"] == final_player["max_health"]
    assert int(_player(desktop(), native_id)["health"]) == int(initial_peer["health"])
    page.screenshot(path=str(output / "progression-combat-status.png"))
    page.locator("canvas").focus()
    page.keyboard.press("c")
    wait("progression_combat_closes_Status", lambda: not web()["ui"]["status"]["visible"])
    return {
        "killed_life_sequences": killed_lives,
        "delayed_hit_seconds": [round(value, 3) for value in delayed_hit_seconds],
        "production_respawn_seconds": [round(value, 3) for value in respawn_seconds],
        "ground_drop_ids": sorted(seen_drop_ids),
        "baseline": baseline,
        "after_quarter": post_quarter,
        "after_vitality": final_progression,
        "player_after_vitality": final_player,
        "peer_progression": _selected_progression(desktop(), native_id),
        "inventory": final_state.get("inventory", []),
        "status": status,
        "taskbar": taskbar,
    }
