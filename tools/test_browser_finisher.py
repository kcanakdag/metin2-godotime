"""Exported-client checks for the protocol-9 Training Grounds finisher slice."""

from __future__ import annotations

import math
import time

from browser_snapshot import POSITION_VALID, subscribed_player_position

DOG_MAX_HEALTH = 100
DOG_HOMES = {1: [3.0, 3.0], 2: [3.25, 3.0], 3: [11.5, 3.0]}
WEB_SAFE = [-18.0, 3.0]
NATIVE_SAFE = [-18.0, 6.0]
PRE_BAIT = [3.125, 18.0]
BAIT = [3.125, 10.5]
MISS_DISTANCE_M = 3.4
PLAYER_MOVE_SPEED_MPS = 5.0
MONSTER_ACQUISITION_M = 8.0
COMBO_1 = "actor.player.warrior-male.onehand.combo_1"
COMBO_2 = "actor.player.warrior-male.onehand.combo_2"
COMBO_3 = "actor.player.warrior-male.onehand.combo_3"
COMBO_4 = "actor.player.warrior-male.onehand.combo_4"
FRONT_KNOCKDOWN = "actor.mob.wild-dog-101.general.front_knockdown"
FRONT_STANDUP = "actor.mob.wild-dog-101.general.front_standup"
BACK_KNOCKDOWN = "actor.mob.wild-dog-101.general.back_knockdown"
DEFINITION_HASH = "8112e4e78e83ed885e6cb2df0c2a15e5aba07c47784169aefa66e7d17a9aedbc"
COMBO_DURATIONS_US = {
    COMBO_1: 1_000_000,
    COMBO_2: 933_333,
    COMBO_3: 1_066_667,
    COMBO_4: 1_266_667,
}
FOLLOWUP_WINDOWS_US = {
    COMBO_1: (167_094, 533_333),
    COMBO_2: (100_513, 543_248),
    COMBO_3: (84_786, 418_462),
}
FOLLOWUP_DELAYS_SECONDS = {COMBO_1: 0.20, COMBO_2: 0.16, COMBO_3: 0.14}
COMBO_4_ROOT_M = 1.1964712524414062
ROOT_TOLERANCE_M = 0.01
RENDER_TOLERANCE_M = 0.05
FORCE_DISTANCE_M = 4.732
# PveActor uses exponential smoothing at 12/s; force advances every 50 ms.
# The quadratic ease-out's maximum speed is 2 * distance / duration (1 s).
# Check moving lag against that bound, then require 5 cm terminal convergence.
FORCE_RENDER_LAG_M = 2.0 * FORCE_DISTANCE_M * (1.0 / 12.0 + 0.05) + RENDER_TOLERANCE_M
TIMING_POLL_SECONDS = 0.01

# Godot's Time.get_ticks_msec() starts from the engine clock, while browser
# performance.now() starts from the page clock.  Do not mix those epochs when
# estimating the age of a published browser probe value.
TARGET_ACK_OBSERVER_SCRIPT = r"""() => {
    const property = "mt2SelectTargetAcks";
    const stateProperty = "__mt2FinisherTargetAckObserver";
    const existing = window[stateProperty];
    if (existing && existing.version === 2) return {installed: true, reused: true};

    const descriptor = Object.getOwnPropertyDescriptor(window, property);
    if (descriptor && !descriptor.configurable) {
        return {installed: false, reason: "non-configurable publication property"};
    }
    let stored = descriptor && "value" in descriptor ? descriptor.value : window[property];
    const read = () => descriptor && descriptor.get ? descriptor.get.call(window) : stored;
    const write = value => {
        if (descriptor && descriptor.set) descriptor.set.call(window, value);
        else stored = value;
    };
    const latestSequence = value => {
        try {
            const rows = JSON.parse(typeof value === "string" ? value : "[]");
            const last = Array.isArray(rows) && rows.length ? rows[rows.length - 1] : {};
            const sequence = Number(last && last.sequence);
            return Number.isSafeInteger(sequence) && sequence >= 0 ? [sequence, last] : null;
        } catch (_) {
            return null;
        }
    };
    const initial = latestSequence(read());
    const state = {
        version: 2,
        latestSequence: initial ? initial[0] : -1,
        firstPublications: {},
        repeatedPublications: 0,
        armedPointer: null,
        pendingPointer: null
    };
    const armPointer = candidate => {
        const x = Number(candidate && candidate.x);
        const y = Number(candidate && candidate.y);
        const button = Number(candidate && candidate.button);
        const expectedSequence = Number(candidate && candidate.expected_sequence);
        if (!Number.isFinite(x) || !Number.isFinite(y) || button !== 0
                || !Number.isSafeInteger(expectedSequence) || expectedSequence < 1) {
            return {armed: false, reason: "invalid target pointer"};
        }
        state.armedPointer = {x, y, button, expectedSequence,
            armed_performance_ms: performance.now()};
        state.pendingPointer = null;
        return {armed: true, armed_performance_ms: state.armedPointer.armed_performance_ms};
    };
    state.arm_pointer = armPointer;
    document.addEventListener("mousedown", event => {
        const armed = state.armedPointer;
        if (!armed || event.button !== armed.button || !(event.target instanceof HTMLCanvasElement)
                || Math.abs(event.clientX - armed.x) > 1 || Math.abs(event.clientY - armed.y) > 1) {
            return;
        }
        state.pendingPointer = {...armed, actual_performance_ms: performance.now(),
            actual_client_x: event.clientX, actual_client_y: event.clientY};
        state.armedPointer = null;
    }, true);
    const observe = value => {
        const latest = latestSequence(value);
        if (!latest) return;
        const [sequence, ack] = latest;
        if (sequence <= state.latestSequence) {
            state.repeatedPublications += 1;
            return;
        }
        state.latestSequence = sequence;
        const pending = state.pendingPointer;
        const matchingPointer = pending
            && sequence === pending.expectedSequence && ack.succeeded === true;
        state.firstPublications[String(sequence)] = {
            sequence,
            reducer_timestamp_us: Number(ack.reducer_timestamp_us),
            published_performance_ms: performance.now(),
            actual_pointer: matchingPointer ? pending : {}
        };
        if (pending && sequence >= pending.expectedSequence) state.pendingPointer = null;
    };
    Object.defineProperty(window, property, {
        configurable: true,
        enumerable: descriptor ? descriptor.enumerable : true,
        get: read,
        set: value => {
            write(value);
            observe(read());
        }
    });
    window[stateProperty] = state;
    return {installed: true, reused: false, initial_sequence: state.latestSequence};
}"""

TARGET_ACK_TIMING_PROJECTION = r"""sequence => {
    const rows = JSON.parse(window.mt2AttackAcks || '[]');
    const observer = window.__mt2FinisherTargetAckObserver || {};
    return {
        performance_now_ms: performance.now(),
        target_ack_publication:
            (observer.firstPublications || {})[String(sequence)] || {},
        target_ack_republications: Number(observer.repeatedPublications || 0),
        attack_ack: Array.isArray(rows) && rows.length ? rows[rows.length - 1] : {}
    };
}"""

WEB_STAGE_STATE_PROJECTION = r"""({ owner, lives }) => {
    const player = JSON.parse(window.mt2OwnPublicAction || '{}');
    const snapshot = JSON.parse(window.mt2Snapshot || '{}');
    const rows = Array.isArray(snapshot.player_rows) ? snapshot.player_rows : [];
    const ownRows = rows.filter(row => row && row.identity === owner).map(row => ({
        ...row, ...player, identity: row.identity, online: row.online,
        x: player.x, y: player.y, z: player.z
    }));
    const history = JSON.parse(window.mt2MonsterActionHistory || '[]');
    const monsters = [];
    for (const targetId of [1, 2]) {
        let newest = null;
        for (let index = history.length - 1; index >= 0; index -= 1) {
            const row = history[index];
            if (row && Number(row.id) === targetId) {
                newest = row;
                break;
            }
        }
        if (newest) monsters.push(newest);
    }
    return {
        observed_performance_ms: performance.now(),
        player_rows: ownRows,
        monsters
    };
}"""


def _web_stage_state_projection(page, owner: str, lives: dict[int, int]) -> dict:
    """Read newest A/B history rows without silently falling back to an older life."""

    value = page.evaluate(
        WEB_STAGE_STATE_PROJECTION,
        {"owner": owner, "lives": {str(target_id): life for target_id, life in lives.items()}},
    )
    assert isinstance(value, dict)
    return value


def _target_ack_timing_projection(page, target_sequence: int) -> dict:
    value = page.evaluate(TARGET_ACK_TIMING_PROJECTION, target_sequence)
    assert isinstance(value, dict)
    return value


def _arm_target_pointer(page, x: float, y: float, expected_sequence: int) -> dict:
    value = page.evaluate(
        """pointer => {
            const observer = window.__mt2FinisherTargetAckObserver;
            return observer && observer.arm_pointer ? observer.arm_pointer(pointer) : {armed: false};
        }""",
        {
            "x": x,
            "y": y,
            "button": 0,
            "expected_sequence": expected_sequence,
        },
    )
    assert isinstance(value, dict) and value.get("armed") is True
    return value


def verify_web_stage_projection(page) -> None:
    """Exercise real Playwright projection positive, missing, and newer-life cases."""

    page.set_content("<!doctype html><title>finisher projection check</title>")
    page.evaluate(
        """() => {
            window.mt2OwnPublicAction = JSON.stringify({x: 3.125, y: 0, z: 10.5});
            window.mt2Snapshot = JSON.stringify({player_rows: [{
                identity: 'synthetic-owner', online: true, x: -18, y: 0, z: 3
            }]});
            window.mt2MonsterActionHistory = JSON.stringify([
                {id: 1, life_sequence: 3, health: 100, x: 3, y: 0, z: 3},
                {id: 2, life_sequence: 7, health: 100, x: 3.25, y: 0, z: 3}
            ]);
        }"""
    )
    lives = {1: 3, 2: 7}
    state = _web_stage_state_projection(page, "synthetic-owner", lives)
    assert _authoritative_xz(state, "synthetic-owner") == [3.125, 10.5]
    assert int(_monster(state, 1).get("life_sequence", -1)) == lives[1]
    assert int(_monster(state, 2).get("life_sequence", -1)) == lives[2]

    for invalid_rows in (
        [],
        [{"identity": "synthetic-owner", "online": False}],
        [{"identity": "synthetic-owner"}],
        [{"identity": "another-player", "online": True}],
    ):
        page.evaluate(
            "rows => window.mt2Snapshot = JSON.stringify({player_rows: rows})", invalid_rows
        )
        assert (
            _authoritative_xz(
                _web_stage_state_projection(page, "synthetic-owner", lives), "synthetic-owner"
            )
            is None
        )
    page.evaluate(
        """() => {
            window.mt2Snapshot = JSON.stringify({player_rows: [{
                identity: 'synthetic-owner', online: true, x: -18, y: 0, z: 3
            }]});
            window.mt2OwnPublicAction = JSON.stringify({x: NaN, y: 0, z: 10.5});
        }"""
    )
    assert (
        _authoritative_xz(
            _web_stage_state_projection(page, "synthetic-owner", lives), "synthetic-owner"
        )
        is None
    )
    page.evaluate("() => window.mt2OwnPublicAction = JSON.stringify({x: 3.125, y: 0, z: 10.5})")

    page.evaluate("() => window.mt2MonsterActionHistory = '[]'")
    missing = _web_stage_state_projection(page, "synthetic-owner", lives)
    assert not _monster(missing, 1) and not _monster(missing, 2)

    page.evaluate(
        """() => window.mt2MonsterActionHistory = JSON.stringify([
            {id: 1, life_sequence: 3, health: 100, x: 3, y: 0, z: 3},
            {id: 1, life_sequence: 4, health: 100, x: 3, y: 0, z: 3},
            {id: 2, life_sequence: 7, health: 100, x: 3.25, y: 0, z: 3}
        ])"""
    )
    newer = _web_stage_state_projection(page, "synthetic-owner", lives)
    assert int(_monster(newer, 1).get("life_sequence", -1)) == 4
    assert int(_monster(newer, 1).get("life_sequence", -1)) != lives[1]
    assert int(_monster(newer, 2).get("life_sequence", -1)) == lives[2]


def verify_target_ack_timing_observer(page) -> None:
    """Check the real capture-phase pointer anchor excludes a delayed pre-call marker."""

    page.set_content(
        """<!doctype html><style>body { margin: 0 }</style>
        <canvas id="target" width="100" height="100"></canvas>"""
    )
    page.evaluate(
        """() => {
            window.mt2SelectTargetAcks = '[]';
            document.querySelector('canvas').addEventListener('mousedown', () => {
                setTimeout(() => window.mt2SelectTargetAcks = JSON.stringify([{
                    succeeded: true, observed_at_ticks_ms: 7,
                    reducer_timestamp_us: 5000000, server_time_us: 5000000,
                    public_action: {}, sequence: 1, combat_target: {}
                }]), 30);
            });
        }"""
    )
    installed = page.evaluate(TARGET_ACK_OBSERVER_SCRIPT)
    assert isinstance(installed, dict) and installed.get("installed") is True
    premouse_ms = float(page.evaluate("() => performance.now()"))
    time.sleep(0.1)
    _arm_target_pointer(page, 20.0, 20.0, 1)
    page.mouse.click(20.0, 20.0)
    page.wait_for_function(
        """() => Boolean(
            window.__mt2FinisherTargetAckObserver?.firstPublications?.['1']
        )"""
    )
    timing = _target_ack_timing_projection(page, 1)
    publication: dict = timing["target_ack_publication"]
    pointer: dict = publication["actual_pointer"]
    now_ms = float(timing["performance_now_ms"])
    actual_ms = float(pointer["actual_performance_ms"])
    published_ms = float(publication["published_performance_ms"])
    assert premouse_ms < actual_ms <= published_ms <= now_ms
    assert actual_ms - premouse_ms >= 75.0
    assert published_ms - actual_ms >= 20.0
    assert now_ms - actual_ms + 50.0 < now_ms - premouse_ms
    assert int(pointer["button"]) == 0
    assert int(pointer["expectedSequence"]) == 1
    assert publication.get("reducer_timestamp_us") == 5_000_000

    _arm_target_pointer(page, 20.0, 20.0, 2)
    page.mouse.click(20.0, 20.0)
    page.wait_for_timeout(40)
    page.evaluate(
        """() => window.mt2SelectTargetAcks = JSON.stringify([{
            succeeded: false, observed_at_ticks_ms: 8,
            reducer_timestamp_us: 5000100, server_time_us: 5000100,
            public_action: {}, sequence: 2, combat_target: {}
        }])"""
    )
    page.wait_for_function(
        """() => Boolean(
            window.__mt2FinisherTargetAckObserver?.firstPublications?.['2']
        )"""
    )
    failed = _target_ack_timing_projection(page, 2)["target_ack_publication"]
    assert failed.get("actual_pointer") == {}

    _arm_target_pointer(page, 20.0, 20.0, 3)
    page.mouse.click(20.0, 20.0)
    page.wait_for_timeout(40)
    page.evaluate(
        """() => window.mt2SelectTargetAcks = JSON.stringify([{
            succeeded: true, observed_at_ticks_ms: 9,
            reducer_timestamp_us: 5000200, server_time_us: 5000200,
            public_action: {}, sequence: 4, combat_target: {}
        }])"""
    )
    page.wait_for_function(
        """() => Boolean(
            window.__mt2FinisherTargetAckObserver?.firstPublications?.['4']
        )"""
    )
    wrong_sequence = _target_ack_timing_projection(page, 4)["target_ack_publication"]
    assert wrong_sequence.get("actual_pointer") == {}


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


def _monster(snapshot: dict, target_id: int) -> dict:
    return next(
        (row for row in snapshot.get("monsters", []) if int(row.get("id", 0)) == target_id),
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


def _finite(values, size: int) -> list[float] | None:
    if (
        not isinstance(values, list)
        or len(values) != size
        or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values)
    ):
        return None
    return [float(value) for value in values]


def _public_xyz(row: dict) -> list[float] | None:
    return _finite([row.get("x"), row.get("y"), row.get("z")], 3)


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
    position = _finite(row.get("position"), 3)
    return [position[0], position[2]] if position is not None else None


def _pick(snapshot: dict, target_id: int, life: int) -> list[float] | None:
    value = _presentation(snapshot, target_id).get("pick", {})
    point = value.get("screen", []) if isinstance(value, dict) else []
    if (
        not isinstance(value, dict)
        or value.get("available") is not True
        or int(value.get("target_id", 0)) != target_id
        or int(value.get("target_life_sequence", -1)) != life
    ):
        return None
    return _finite(point, 2)


def _last(rows) -> dict:
    return rows[-1] if isinstance(rows, list) and rows and isinstance(rows[-1], dict) else {}


def _health_history(snapshot: dict, target_id: int, life: int) -> list[int]:
    result: list[int] = []
    for row in snapshot.get("monster_health_history", []):
        if (
            isinstance(row, dict)
            and int(row.get("id", 0)) == target_id
            and int(row.get("life_sequence", -1)) == life
            and isinstance(row.get("health"), int)
        ):
            health = int(row["health"])
            if not result or result[-1] != health:
                result.append(health)
    return result


def _monster_history(snapshot: dict, target_id: int, life: int) -> list[dict]:
    return [
        row
        for row in snapshot.get("monster_action_history", [])
        if isinstance(row, dict)
        and int(row.get("id", 0)) == target_id
        and int(row.get("life_sequence", -1)) == life
        and _public_xyz(row) is not None
    ]


def _force_render_observation(snapshot: dict, start: dict) -> dict:
    target_id = int(start["id"])
    current = _monster(snapshot, target_id)
    presentation = next(
        (row for row in snapshot.get("rendered_monsters", []) if row.get("row_id") == target_id),
        {},
    )
    current_xyz, start_xyz = _public_xyz(current), _public_xyz(start)
    rendered = _rendered_xz(snapshot, "rendered_monsters", "row_id", target_id)
    result = {"valid": False, "current": current, "rendered": presentation}
    if current_xyz is None or start_xyz is None or rendered is None:
        return result
    if (
        any(
            current.get(key) != start.get(key)
            for key in ("life_sequence", "attack_sequence", "action_started_at_us")
        )
        or current.get("attack_action_id") != FRONT_KNOCKDOWN
        or presentation.get("action_id") != FRONT_KNOCKDOWN
        or presentation.get("attack_sequence") != start.get("attack_sequence")
    ):
        return result
    delta = [current_xyz[0] - start_xyz[0], current_xyz[2] - start_xyz[2]]
    distance = math.hypot(*delta)
    if distance < 0.5:
        return result
    visual = [rendered[0] - start_xyz[0], rendered[1] - start_xyz[2]]
    along = sum(visual[index] * delta[index] for index in range(2)) / distance
    cross = abs(visual[0] * delta[1] - visual[1] * delta[0]) / distance
    lag = math.dist(rendered, [current_xyz[0], current_xyz[2]])
    result.update(
        authoritative_distance_m=distance,
        rendered_along_m=along,
        rendered_cross_m=cross,
        lag_m=lag,
        lag_limit_m=FORCE_RENDER_LAG_M,
        valid=(
            0.5 <= along <= distance + RENDER_TOLERANCE_M
            and cross <= RENDER_TOLERANCE_M
            and lag <= FORCE_RENDER_LAG_M
        ),
    )
    return result


def _player_history(snapshot: dict, identity: str, action_id: str, sequence: int) -> list[dict]:
    result: list[dict] = []
    for entry in snapshot.get("public_action_history", []):
        if not isinstance(entry, dict) or entry.get("identity") != identity:
            continue
        action = entry.get("public_action", {})
        if (
            isinstance(action, dict)
            and action.get("attack_action_id") == action_id
            and int(action.get("attack_sequence", -1)) == sequence
            and _public_xyz(action) is not None
        ):
            result.append(entry)
    return result


def _forward(heading: float) -> list[float]:
    return [-math.sin(heading), -math.cos(heading)]


def park_finisher_clients(
    web,
    desktop,
    web_command,
    native_command,
    wait,
    web_id: str,
    native_id: str,
) -> dict:
    """Promptly move both fresh Training characters outside monster chase range."""

    # Issue both ordinary movement intents before waiting for either client. This
    # avoids leaving the second fresh character at the aggro-adjacent spawn while
    # the first character completes its long escape route.
    web_command("target", x=WEB_SAFE[0], z=WEB_SAFE[1])
    native_command("target", x=NATIVE_SAFE[0], z=NATIVE_SAFE[1])

    def both_arrived() -> bool:
        local, peer = web(), desktop()
        web_local = _authoritative_xz(local, web_id)
        web_peer = _authoritative_xz(peer, web_id)
        native_local = _authoritative_xz(peer, native_id)
        native_peer = _authoritative_xz(local, native_id)
        return (
            web_local is not None
            and web_peer is not None
            and native_local is not None
            and native_peer is not None
            and math.dist(web_local, WEB_SAFE) < 0.08
            and math.dist(web_peer, WEB_SAFE) < 0.08
            and math.dist(native_local, NATIVE_SAFE) < 0.08
            and math.dist(native_peer, NATIVE_SAFE) < 0.08
        )

    wait("finisher_both_fresh_characters_promptly_reach_safe_positions", both_arrived, 12)
    web_command("stop")
    native_command("stop")

    parked: dict = {}

    def both_stopped() -> bool:
        nonlocal parked
        local, peer = web(), desktop()
        valid = (
            int(_player(local, web_id).get("activity", -1)) == 0
            and int(_player(peer, web_id).get("activity", -1)) == 0
            and int(_player(local, native_id).get("activity", -1)) == 0
            and int(_player(peer, native_id).get("activity", -1)) == 0
        )
        if valid:
            parked = {"web": local, "native": peer}
        return valid

    wait("finisher_both_fresh_characters_stop_at_safe_positions", both_stopped, 3)
    return parked


def heal_finisher_browser(page, web, wait, web_id: str) -> dict:
    """Restore setup damage through the ordinary visible potion inventory action."""

    initial = web()
    player = _player(initial, web_id)
    before_health = int(player.get("health", 0))
    max_health = int(player.get("max_health", 0))
    potion = next(
        (row for row in initial.get("inventory", []) if int(row.get("vnum", 0)) == 27001),
        {},
    )
    before_count = int(potion.get("count", 0))
    assert 0 < before_health <= max_health and before_count > 0
    if before_health == max_health:
        return {
            "before_health": before_health,
            "after_health": before_health,
            "max_health": max_health,
            "before_potions": before_count,
            "after_potions": before_count,
            "visible_uses": 0,
        }
    required_uses = math.ceil((max_health - before_health) / 40)
    assert required_uses < before_count, (
        "Finisher entry damage requires more visible healing than leaves one starter potion "
        "for the full-health inventory rejection"
    )

    page.keyboard.press("i")
    wait("finisher_healing_inventory_opens", lambda: bool(web()["ui"].get("visible")), 3)
    state = web()
    potion = next(row for row in state["inventory"] if int(row.get("vnum", 0)) == 27001)
    cell = int(potion["cell"])
    page_index = cell // 45
    ui = state["ui"]
    if int(ui.get("page", -1)) != page_index:
        page.mouse.click(*ui["tab_centers"][page_index])
        wait(
            "finisher_healing_potion_page_opens",
            lambda: int(web()["ui"].get("page", -1)) == page_index,
            3,
        )
        ui = web()["ui"]
    origin = ui["grid_origin"]
    point = [origin[0] + (cell % 5) * 32 + 16, origin[1] + (cell % 45 // 5) * 32 + 16]

    visible_uses = 0
    current_health = before_health
    current_count = before_count
    while visible_uses < required_uses:
        page.mouse.click(*point, button="right")
        expected_health = min(current_health + 40, max_health)
        expected_count = current_count - 1
        wait(
            f"finisher_visible_potion_{visible_uses + 1}_restores_server_health",
            lambda expected_health=expected_health, expected_count=expected_count: (
                int(_player(web(), web_id).get("health", -1)) == expected_health
                and int(
                    next(
                        row
                        for row in web().get("inventory", [])
                        if int(row.get("vnum", 0)) == 27001
                    ).get("count", -1)
                )
                == expected_count
            ),
            3,
        )
        visible_uses += 1
        current_health = expected_health
        current_count = expected_count
        if current_health < max_health:
            time.sleep(1.01)
    page.keyboard.press("Escape")
    wait("finisher_healing_inventory_closes", lambda: not bool(web()["ui"].get("visible")), 3)
    return {
        "before_health": before_health,
        "after_health": current_health,
        "max_health": max_health,
        "before_potions": before_count,
        "after_potions": current_count,
        "visible_uses": visible_uses,
    }


def exercise_finisher(
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
    """Exercise combo4, area damage, reactions, force, and camera presentation."""

    started = time.monotonic()
    phase = "initial"
    trace: list[dict] = []
    evidence: dict[str, object] = {}
    diagnostics.clear()
    diagnostics.update({"phase": phase, "trace": trace, "evidence": evidence})
    read_web, read_desktop = web, desktop

    def observe(side: str, snapshot: dict) -> dict:
        owner = web_id if side == "web" else native_id
        trace.append(
            {
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "phase": phase,
                "side": side,
                "connection_state": snapshot.get("connection_state"),
                "owner": {
                    key: _player(snapshot, owner).get(key)
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
                "monsters": [
                    {
                        key: row.get(key)
                        for key in (
                            "id",
                            "life_sequence",
                            "health",
                            "activity",
                            "attack_action_id",
                            "attack_sequence",
                            "x",
                            "y",
                            "z",
                        )
                    }
                    for row in snapshot.get("monsters", [])
                    if isinstance(row, dict)
                ],
                "combat_target": snapshot.get("combat_target", {}),
                "screen_wave": snapshot.get("screen_wave", {}),
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

    def poll(predicate, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(TIMING_POLL_SECONDS)
        return False

    def last_attack_ack() -> dict:
        value = page.evaluate("() => JSON.parse(window.mt2AttackAcks || '[]')")
        return _last(value)

    def last_target_ack() -> dict:
        value = page.evaluate("() => JSON.parse(window.mt2SelectTargetAcks || '[]')")
        return _last(value)

    def install_target_ack_observer() -> dict:
        value = page.evaluate(TARGET_ACK_OBSERVER_SCRIPT)
        assert isinstance(value, dict) and value.get("installed") is True, (
            "Could not observe browser target ACK publications: " + str(value)
        )
        return value

    def browser_timing_projection(target_sequence: int) -> dict:
        return _target_ack_timing_projection(page, target_sequence)

    def own_action() -> dict:
        value = page.evaluate("() => JSON.parse(window.mt2OwnPublicAction || '{}')")
        return value if isinstance(value, dict) else {}

    def wave_history_web() -> list[dict]:
        value = page.evaluate("() => JSON.parse(window.mt2ScreenWaveHistory || '[]')")
        return value if isinstance(value, list) else []

    def web_pick_projection(target_id: int) -> dict:
        value = page.evaluate(
            """targetId => {
                const snapshot = JSON.parse(window.mt2Snapshot || '{}');
                const exact = (name, key) => {
                    const rows = Array.isArray(snapshot[name]) ? snapshot[name] : [];
                    return rows.filter(row => row && row[key] === targetId);
                };
                return {
                    combat_target: snapshot.combat_target || {},
                    monsters: exact('monsters', 'id'),
                    monster_presentations: exact('monster_presentations', 'row_id'),
                    ui: snapshot.ui || {}
                };
            }""",
            target_id,
        )
        assert isinstance(value, dict)
        return value

    def move(side: str, owner: str, destination: list[float], label: str, timeout=12) -> None:
        command = web_command if side == "web" else native_command
        local = web if side == "web" else desktop
        peer = desktop if side == "web" else web
        command("target", x=destination[0], z=destination[1])
        wait(
            label + "_arrives_on_both_subscriptions",
            lambda: (
                (first := _authoritative_xz(local(), owner)) is not None
                and (second := _authoritative_xz(peer(), owner)) is not None
                and math.dist(first, destination) < 0.08
                and math.dist(second, destination) < 0.08
            ),
            timeout,
        )
        command("stop")
        wait(
            label + "_stops",
            lambda: int(_player(local(), owner).get("activity", -1)) == 0,
            3,
        )

    def ui_state() -> dict:
        value = page.evaluate(
            """() => {
                const snapshot = JSON.parse(window.mt2Snapshot || '{}');
                return {ui: snapshot.ui || {}, inventory: snapshot.inventory || []};
            }"""
        )
        assert isinstance(value, dict)
        return value

    def sword(snapshot: dict) -> dict:
        return next(row for row in snapshot.get("inventory", []) if int(row.get("vnum", 0)) == 10)

    def inventory_cell(ui: dict, cell: int) -> list[float]:
        origin = ui["grid_origin"]
        return [origin[0] + (cell % 5) * 32 + 16, origin[1] + (cell % 45 // 5) * 32 + 16]

    def set_inventory_open(visible: bool) -> dict:
        state = ui_state()
        if bool(state["ui"].get("visible")) != visible:
            page.keyboard.press("i")
            wait(
                "finisher_inventory_" + ("opens" if visible else "closes"),
                lambda: bool(ui_state()["ui"].get("visible")) is visible,
                3,
                TIMING_POLL_SECONDS,
            )
        return ui_state()

    initial_ui = ui_state()
    original_sword = sword(initial_ui).copy()
    assert not bool(original_sword.get("equipped"))
    original_cell = int(original_sword["cell"])
    original_page = int(initial_ui["ui"].get("page", 0))

    def equip() -> None:
        state = set_inventory_open(True)
        current_sword = sword(state)
        assert current_sword["id"] == original_sword["id"] and not current_sword["equipped"]
        cell = int(current_sword["cell"])
        page_index = cell // 45
        if int(state["ui"].get("page", -1)) != page_index:
            page.mouse.click(*state["ui"]["tab_centers"][page_index])
            wait(
                "finisher_original_sword_page_opens",
                lambda: int(ui_state()["ui"].get("page", -1)) == page_index,
            )
            state = ui_state()
        page.mouse.click(*inventory_cell(state["ui"], cell), button="right")
        wait(
            "finisher_Sword_plus_0_equips_and_projects",
            lambda: (
                bool(sword(web()).get("equipped"))
                and int(_actor(web(), web_id).get("weapon_vnum", 0)) == 10
                and int(_actor(desktop(), web_id).get("weapon_vnum", 0)) == 10
            ),
        )
        set_inventory_open(False)

    def unequip_fast(equipment_center: list[float]) -> float:
        page.keyboard.press("i")
        wait(
            "finisher_inventory_opens_for_pre_area_unequip",
            lambda: bool(ui_state()["ui"].get("visible")),
            1,
            TIMING_POLL_SECONDS,
        )
        sent_at = time.monotonic()
        page.mouse.click(*equipment_center, button="right")
        return sent_at

    def restore_inventory() -> None:
        state = set_inventory_open(True)
        if bool(sword(web()).get("equipped")):
            equipment = state["ui"]["equipment_origin"]
            page.mouse.click(equipment[0] + 16, equipment[1] + 16, button="right")
        wait("finisher_sword_returns_to_bag", lambda: not bool(sword(web()).get("equipped")))
        state = ui_state()
        current_cell = int(sword(state)["cell"])
        if current_cell != original_cell:
            # Equipment right-click chooses the first free bag cell. Restore
            # the test's incoming slot explicitly through click-to-carry UI.
            current_page = current_cell // 45
            if int(state["ui"].get("page", -1)) != current_page:
                page.mouse.click(*state["ui"]["tab_centers"][current_page])
                wait(
                    "finisher_returned_sword_page_opens",
                    lambda: int(ui_state()["ui"].get("page", -1)) == current_page,
                )
            page.mouse.click(*inventory_cell(ui_state()["ui"], current_cell))
            destination_page = original_cell // 45
            if current_page != destination_page:
                page.mouse.click(*ui_state()["ui"]["tab_centers"][destination_page])
                wait(
                    "finisher_sword_restore_destination_page_opens",
                    lambda: int(ui_state()["ui"].get("page", -1)) == destination_page,
                )
            page.mouse.click(*inventory_cell(ui_state()["ui"], original_cell))
        wait(
            "finisher_original_sword_cell_restores",
            lambda: (
                not bool(sword(web()).get("equipped"))
                and int(sword(web()).get("cell", -1)) == original_cell
                and int(_actor(desktop(), web_id).get("weapon_vnum", -1)) == 0
            ),
        )
        state = ui_state()
        if int(state["ui"].get("page", -1)) != original_page:
            page.mouse.click(*state["ui"]["tab_centers"][original_page])
            wait(
                "finisher_incoming_inventory_page_restores",
                lambda: int(ui_state()["ui"].get("page", -1)) == original_page,
            )
        set_inventory_open(False)

    def wait_attack_ack(after: int, succeeded: bool, label: str) -> dict:
        found: dict = {}

        def ready() -> bool:
            nonlocal found
            ack = last_attack_ack()
            sequence = int(ack.get("sequence", 0))
            if sequence <= after:
                return False
            found = ack.copy()
            if sequence != after + 1:
                raise AssertionError("Finisher attack ACK skipped the exact next completion")
            if bool(found.get("succeeded")) is not succeeded:
                raise AssertionError("Finisher attack ACK had the wrong typed outcome")
            if int(found.get("reducer_timestamp_us", 0)) <= 0:
                raise AssertionError("Finisher attack ACK omitted its server receipt timestamp")
            return True

        wait(label, ready, 3, TIMING_POLL_SECONDS)
        return found

    def wait_target_ack(after: int, target_id: int, life: int) -> dict:
        found: dict = {}
        observation = {
            "after_sequence": after,
            "requested_target_id": target_id,
            "requested_life_sequence": life,
        }
        evidence.setdefault("target_ack_observations", []).append(observation)

        def completion_ready() -> bool:
            nonlocal found
            ack = last_target_ack()
            sequence = int(ack.get("sequence", 0))
            if sequence <= after:
                return False
            found = ack.copy()
            observation["completion"] = found.copy()
            if sequence != after + 1 or not bool(found.get("succeeded")):
                raise AssertionError("Exact finisher target selection was rejected or skipped")
            if int(found.get("reducer_timestamp_us", 0)) <= 0:
                raise AssertionError("Accepted finisher target ACK omitted its server timestamp")
            return True

        wait(
            "finisher_exact_next_target_selection_ACK_is_accepted",
            completion_ready,
            3,
            TIMING_POLL_SECONDS,
        )

        subscribed_target: dict = {}

        def subscription_ready() -> bool:
            nonlocal subscribed_target
            target = web_pick_projection(target_id).get("combat_target", {})
            if not isinstance(target, dict):
                return False
            if (
                int(target.get("target_id", 0)) != target_id
                or int(target.get("target_life_sequence", -1)) != life
            ):
                return False
            subscribed_target = target.copy()
            return True

        wait(
            "finisher_exact_life_target_subscription_follows_ACK",
            subscription_ready,
            3,
            TIMING_POLL_SECONDS,
        )
        observation["subscribed_combat_target"] = subscribed_target
        found["subscribed_combat_target"] = subscribed_target
        return found

    def wait_action(action_id: str, sequence: int, label: str) -> dict:
        found: dict = {}

        def ready() -> bool:
            nonlocal found
            row = own_action()
            if (
                int(row.get("activity", -1)) == 2
                and row.get("attack_action_id") == action_id
                and int(row.get("attack_sequence", -1)) == sequence
            ):
                found = row.copy()
                return True
            return False

        wait(label, ready, 3, TIMING_POLL_SECONDS)
        return found

    def press_space(ensure_focus: bool = False) -> None:
        if ensure_focus:
            page.locator("canvas").focus()
        page.keyboard.press("Space")

    def send_followup(previous: dict, previous_ack: dict, action_id: str) -> tuple[dict, dict]:
        deadline = time.monotonic() + FOLLOWUP_DELAYS_SECONDS[action_id]
        time.sleep(max(0.0, deadline - time.monotonic()))
        sent_at = time.monotonic()
        press_space()
        ack = wait_attack_ack(
            int(previous_ack["sequence"]),
            True,
            "finisher_" + action_id.rsplit(".", 1)[-1] + "_links",
        )
        receipt_elapsed_us = int(ack["reducer_timestamp_us"]) - int(
            previous["action_started_at_us"]
        )
        lower, upper = FOLLOWUP_WINDOWS_US[action_id]
        evidence.setdefault("followup_timing", []).append(
            {
                "from_action": action_id,
                "sent_elapsed_seconds": round(sent_at - started, 3),
                "receipt_elapsed_us": receipt_elapsed_us,
                "window_us": [lower, upper],
                "ack": ack,
            }
        )
        assert lower < receipt_elapsed_us <= upper, (
            "Finisher follow-up receipt must stay inside its exact source-defined queue window"
        )
        assert ack.get("public_action", {}).get("attack_action_id") == action_id
        next_id = {COMBO_1: COMBO_2, COMBO_2: COMBO_3, COMBO_3: COMBO_4}[action_id]
        next_action = wait_action(
            next_id,
            int(previous["attack_sequence"]) + 1,
            "finisher_" + next_id.rsplit(".", 1)[-1] + "_own_transition_is_subscribed",
        )
        return ack, next_action

    set_phase("training_fixture")
    first_web, first_native = web(), desktop()
    for snapshot in (first_web, first_native):
        assert (
            snapshot.get("definition_hash") == DEFINITION_HASH
            and int(snapshot.get("obstacles", -1)) == 5
            and snapshot.get("map_chunks") == []
        ), "Finisher export QA requires the exact protocol-9 Training fixture"
        assert len(snapshot.get("monsters", [])) == 3
        for target_id, _home in DOG_HOMES.items():
            dog = _monster(snapshot, target_id)
            assert (
                dog.get("definition_vnum") == 101
                and dog.get("name") == "Wild Dog"
                and int(dog.get("max_health", 0)) == DOG_MAX_HEALTH
            )
    assert all(
        1.9 < math.dist(BAIT, home) < 8.0 for target_id, home in DOG_HOMES.items() if target_id < 3
    ), "Finisher bait must enter A/B acquisition without starting inside attack reach"
    move("web", web_id, WEB_SAFE, "finisher_browser_parks_outside_chase")
    move("native", native_id, NATIVE_SAFE, "finisher_native_parks_outside_chase")

    equip()
    startup_normalization: list[dict] = []

    def wait_home(target_id: int, life: int, health: int, label: str, timeout: float) -> dict:
        found: dict = {}

        def ready() -> bool:
            nonlocal found
            local, peer = web(), desktop()
            first, second = _monster(local, target_id), _monster(peer, target_id)
            valid = (
                int(first.get("life_sequence", -1)) == int(second.get("life_sequence", -2)) == life
                and int(first.get("health", -1)) == int(second.get("health", -2)) == health
                and int(first.get("activity", -1)) == int(second.get("activity", -2)) == 0
                and math.dist([float(first["x"]), float(first["z"])], DOG_HOMES[target_id]) < 0.15
            )
            if valid:
                found = local
            return valid

        wait(label, ready, timeout)
        return found

    for target_id in (1, 2):
        startup = _monster(web(), target_id)
        startup_life = int(startup.get("life_sequence", -1))
        startup_health = int(startup.get("health", -1))
        assert startup_life >= 0 and 0 <= startup_health <= DOG_MAX_HEALTH
        record: dict = {
            "target_id": target_id,
            "initial_life_sequence": startup_life,
            "initial_health": startup_health,
        }
        if startup_health == 0:
            wait_home(
                target_id,
                startup_life + 1,
                DOG_MAX_HEALTH,
                f"finisher_startup_dead_{target_id}_naturally_respawns",
                16,
            )
            record["normalization"] = "natural_respawn"
        elif startup_health < DOG_MAX_HEALTH:
            assert startup_health in (30, 65), (
                "Finisher startup recovery only accepts exact prior combo/area damage states"
            )
            wait_home(
                target_id,
                startup_life,
                startup_health,
                f"finisher_startup_injured_{target_id}_returns_home",
                8,
            )
            move(
                "web",
                web_id,
                DOG_HOMES[target_id],
                f"finisher_startup_approaches_injured_{target_id}",
                8,
            )
            pick_point: list[float] | None = None

            def startup_pick_ready(
                target_id: int = target_id, startup_life: int = startup_life
            ) -> bool:
                nonlocal pick_point
                pick_point = _pick(web(), target_id, startup_life)
                return pick_point is not None

            wait(
                f"finisher_startup_injured_{target_id}_exact_life_pick_renders",
                startup_pick_ready,
                3,
            )
            assert pick_point is not None
            target_ack_before = int(last_target_ack().get("sequence", 0))
            page.mouse.click(*pick_point)
            selection_ack = wait_target_ack(target_ack_before, target_id, startup_life)
            first_ack_before = int(last_attack_ack().get("sequence", 0))
            press_space(True)
            recovery_first_ack = wait_attack_ack(
                first_ack_before,
                True,
                f"finisher_startup_injured_{target_id}_first_attack_is_accepted",
            )
            if startup_health == 65:
                recovery_first = recovery_first_ack["public_action"]
                send_followup(recovery_first, recovery_first_ack, COMBO_1)
            wait(
                f"finisher_startup_injured_{target_id}_ordinary_damage_defeats_exact_life",
                lambda target_id=target_id: (
                    int(_monster(web(), target_id).get("health", -1)) == 0
                    and int(_monster(desktop(), target_id).get("health", -1)) == 0
                ),
                4,
            )
            move(
                "web",
                web_id,
                WEB_SAFE,
                f"finisher_startup_recovery_{target_id}_returns_outside_chase",
            )
            wait_home(
                target_id,
                startup_life + 1,
                DOG_MAX_HEALTH,
                f"finisher_startup_recovery_{target_id}_naturally_respawns",
                16,
            )
            record.update(
                {
                    "normalization": "ordinary_visible_combat_then_natural_respawn",
                    "selection_ack": selection_ack,
                    "first_attack_ack": recovery_first_ack,
                }
            )
        else:
            record["normalization"] = "already_healthy"
        startup_normalization.append(record)
    evidence["startup_normalization"] = startup_normalization
    assert int(_monster(web(), 3).get("health", -1)) == DOG_MAX_HEALTH, (
        "Startup normalization must leave outside C untouched"
    )

    stable_since: float | None = None

    def fixture_stable() -> bool:
        nonlocal stable_since
        snapshots = [web(), desktop()]
        valid = True
        for snapshot in snapshots:
            for target_id, home in DOG_HOMES.items():
                dog = _monster(snapshot, target_id)
                valid = valid and (
                    int(dog.get("health", 0)) == DOG_MAX_HEALTH
                    and int(dog.get("activity", -1)) == 0
                    and math.dist([float(dog["x"]), float(dog["z"])], home) < 0.1
                )
        now = time.monotonic()
        if not valid:
            stable_since = None
            return False
        if stable_since is None:
            stable_since = now
            return False
        return now - stable_since >= 0.5

    wait("finisher_three_healthy_dogs_stabilize_after_both_players_park", fixture_stable, 16)
    initial_lives = {
        target_id: int(_monster(web(), target_id)["life_sequence"]) for target_id in DOG_HOMES
    }
    native_wave_baseline = int(desktop().get("screen_wave", {}).get("trigger_count", 0))
    stage_geometry = {
        "pre_bait": PRE_BAIT,
        "bait": BAIT,
        "pre_bait_A_distance_m": math.dist(PRE_BAIT, DOG_HOMES[1]),
        "pre_bait_B_distance_m": math.dist(PRE_BAIT, DOG_HOMES[2]),
        "bait_A_distance_m": math.dist(BAIT, DOG_HOMES[1]),
        "bait_B_distance_m": math.dist(BAIT, DOG_HOMES[2]),
        "bait_C_distance_m": math.dist(BAIT, DOG_HOMES[3]),
    }
    assert (
        stage_geometry["pre_bait_A_distance_m"] > MONSTER_ACQUISITION_M
        and stage_geometry["pre_bait_B_distance_m"] > MONSTER_ACQUISITION_M
        and abs(stage_geometry["bait_A_distance_m"] - stage_geometry["bait_B_distance_m"]) < 1e-9
        and stage_geometry["bait_A_distance_m"] < MONSTER_ACQUISITION_M
        and stage_geometry["bait_C_distance_m"] > MONSTER_ACQUISITION_M
    ), "The finisher staging route must acquire only the symmetric A/B pair at its bait"
    evidence["stage_geometry"] = stage_geometry

    def web_stage_state() -> dict:
        value = _web_stage_state_projection(page, web_id, initial_lives)
        for target_id in (1, 2):
            row = _monster(value, target_id)
            assert row and int(row.get("life_sequence", -1)) == initial_lives[target_id], (
                "The immediate stage projection has no current expected-life monster row"
            )
        return value

    attack_lock_state: dict = {}
    attack_lock_whiff: list[float] | None = None
    attack_lock_travel_m = 0.0
    attack_lock_required_us = 0
    latest_attack_lock_candidate: dict = {}
    best_attack_lock_candidate: dict = {}
    clock_anchor_server_us = 0
    clock_anchor_monotonic = 0.0

    def estimated_server_time_us() -> int:
        if clock_anchor_server_us <= 0 or clock_anchor_monotonic <= 0:
            return 0
        return clock_anchor_server_us + round(
            (time.monotonic() - clock_anchor_monotonic) * 1_000_000
        )

    def attack_lock() -> bool:
        nonlocal attack_lock_required_us
        nonlocal attack_lock_state
        nonlocal attack_lock_travel_m
        nonlocal attack_lock_whiff
        nonlocal latest_attack_lock_candidate
        nonlocal best_attack_lock_candidate
        state = web_stage_state()
        estimated_clock = estimated_server_time_us()
        a, b = _monster(state, 1), _monster(state, 2)
        actor_xz = _authoritative_xz(state, web_id)
        a_xz = _finite([a.get("x"), a.get("z")], 2)
        b_xz = _finite([b.get("x"), b.get("z")], 2)
        if actor_xz is None or a_xz is None or b_xz is None:
            latest_attack_lock_candidate = {
                "projection_source": "immediate_web_subscription_history",
                "estimated_server_time_us": estimated_clock,
                "missing_positions": True,
            }
            return False
        away = [actor_xz[0] - a_xz[0], actor_xz[1] - a_xz[1]]
        length = math.hypot(*away)
        if length <= 0:
            latest_attack_lock_candidate = {
                "projection_source": "immediate_web_subscription_history",
                "estimated_server_time_us": estimated_clock,
                "zero_away_vector": True,
            }
            return False
        whiff = [
            a_xz[0] + away[0] / length * MISS_DISTANCE_M,
            a_xz[1] + away[1] / length * MISS_DISTANCE_M,
        ]
        travel_m = math.dist(actor_xz, whiff)
        required_us = math.ceil(travel_m / PLAYER_MOVE_SPEED_MPS * 1_000_000) + 400_000
        valid = (
            estimated_clock > 0
            and int(a.get("activity", -1)) == 2
            and int(a.get("action_ends_at_us", 0)) - estimated_clock >= required_us
            and int(b.get("health", -1)) == DOG_MAX_HEALTH
            and int(b.get("activity", -1)) == 2
            and math.dist(a_xz, b_xz) <= 0.5
        )
        candidate = {
            "projection_source": "immediate_web_subscription_history",
            "observed_performance_ms": state.get("observed_performance_ms"),
            "estimated_server_time_us": estimated_clock,
            "travel_m": travel_m,
            "required_remaining_us": required_us,
            "A_remaining_us": int(a.get("action_ends_at_us", 0)) - estimated_clock,
            "A_activity": a.get("activity"),
            "B_activity": b.get("activity"),
            "B_health": b.get("health"),
            "A_B_distance_m": math.dist(a_xz, b_xz),
            "valid": valid,
        }
        latest_attack_lock_candidate = candidate
        if int(candidate["A_remaining_us"]) > int(
            best_attack_lock_candidate.get("A_remaining_us", -1)
        ):
            best_attack_lock_candidate = candidate
        if valid:
            attack_lock_state = state
            attack_lock_whiff = whiff
            attack_lock_travel_m = travel_m
            attack_lock_required_us = required_us
        return valid

    last_whiff_state: dict = {}
    last_whiff_clock_us = 0
    last_whiff_observed_at = 0.0
    critical_whiff: list[float] | None = None

    def whiff_stable() -> bool:
        nonlocal last_whiff_clock_us
        nonlocal last_whiff_observed_at
        nonlocal last_whiff_state
        state = web_stage_state()
        actor_position = _authoritative_xz(state, web_id)
        actor = _player(state, web_id)
        estimated_clock = estimated_server_time_us()
        valid = (
            actor_position is not None
            and critical_whiff is not None
            and math.dist(actor_position, critical_whiff) < 0.08
            and int(actor.get("activity", -1)) == 0
            and estimated_clock > 0
            and int(_monster(state, 1).get("activity", -1)) == 2
            and int(_monster(state, 1).get("action_ends_at_us", 0)) - estimated_clock >= 400_000
            and int(_monster(state, 2).get("health", -1)) == DOG_MAX_HEALTH
            and math.dist(
                [float(_monster(state, 1)["x"]), float(_monster(state, 1)["z"])],
                [float(_monster(state, 2)["x"]), float(_monster(state, 2)["z"])],
            )
            <= 0.5
            and math.dist(
                actor_position, [float(_monster(state, 1)["x"]), float(_monster(state, 1)["z"])]
            )
            >= 3.3
        )
        if valid:
            last_whiff_state = state
            last_whiff_clock_us = estimated_clock
            last_whiff_observed_at = time.monotonic()
        return valid

    set_phase("first_whiff_stage")
    stage_attempts: list[dict] = []
    staged = False
    selected_point: list[float] | None = None
    selection_ack: dict = {}
    equipment_center: list[float] | None = None
    close_center: list[float] | None = None
    selection_input_performance_ms = -1.0
    first_ack_before = 0
    for attempt in range(1, 4):
        latest_attack_lock_candidate = {}
        best_attack_lock_candidate = {}
        move(
            "web",
            web_id,
            PRE_BAIT,
            f"finisher_browser_reaches_safe_pre_bait_attempt_{attempt}",
            8,
        )
        move(
            "web",
            web_id,
            BAIT,
            f"finisher_browser_reaches_attack_bait_attempt_{attempt}",
            8,
        )

        # Resolve the rendered target and cache both later UI controls before
        # waiting for the fresh attack lock that governs the timed retreat.
        if not selection_ack:

            def exact_pick_ready() -> bool:
                nonlocal selected_point
                selected = web_pick_projection(1)
                selected_point = _pick(selected, 1, initial_lives[1])
                return selected_point is not None

            assert poll(exact_pick_ready, 3), (
                "The current exact-life A pick was unavailable at the attack bait"
            )
            assert selected_point is not None
            target_ack_observer = install_target_ack_observer()
            target_ack_before = int(last_target_ack().get("sequence", 0))
            selection_input_performance_ms = float(page.evaluate("() => performance.now()"))
            assert math.isfinite(selection_input_performance_ms)
            pointer_arm = _arm_target_pointer(
                page, selected_point[0], selected_point[1], target_ack_before + 1
            )
            page.mouse.click(*selected_point)
            selection_ack = wait_target_ack(target_ack_before, 1, initial_lives[1])
            assert int(selection_ack.get("reducer_timestamp_us", 0)) > 0

            selected_ui: dict = {}

            def controls_ready() -> bool:
                nonlocal selected_ui
                selected_ui = web_pick_projection(1)["ui"]
                return (
                    _finite(selected_ui.get("equipment_origin"), 2) is not None
                    and _finite(selected_ui.get("target", {}).get("close_center"), 2) is not None
                )

            assert poll(controls_ready, 2), (
                "Accepted A selection did not expose the fixed target/equipment controls"
            )
            equipment_origin = _finite(selected_ui.get("equipment_origin"), 2)
            close_center = _finite(selected_ui.get("target", {}).get("close_center"), 2)
            assert equipment_origin is not None and close_center is not None
            equipment_center = [equipment_origin[0] + 16, equipment_origin[1] + 16]
            evidence["selection"] = {
                "screen": selected_point,
                "premouse_input_performance_ms": selection_input_performance_ms,
                "pointer_arm": pointer_arm,
                "ack": selection_ack,
                "target_ack_observer": target_ack_observer,
            }

        # Establish canvas focus and the exact ACK baseline before waiting for a
        # fresh monster lock. Playwright's focus action can take hundreds of
        # milliseconds in an exported browser; doing it after the timed retreat
        # consumed the otherwise valid whiff margin in the retained replay.
        page.locator("canvas").focus()
        projection_requested_at = time.monotonic()
        timing_projection = browser_timing_projection(int(selection_ack["sequence"]))
        projection_received_at = time.monotonic()
        browser_ticks_ms = float(timing_projection.get("performance_now_ms", -1))
        publication = timing_projection.get("target_ack_publication", {})
        publication_ticks_ms = float(publication.get("published_performance_ms", -1))
        publication_timestamp_us = int(publication.get("reducer_timestamp_us", 0))
        actual_pointer = publication.get("actual_pointer", {})
        actual_pointer_ms = float(actual_pointer.get("actual_performance_ms", -1))
        actual_pointer_x = float(actual_pointer.get("actual_client_x", math.nan))
        actual_pointer_y = float(actual_pointer.get("actual_client_y", math.nan))
        assert (
            math.isfinite(browser_ticks_ms)
            and browser_ticks_ms
            >= publication_ticks_ms
            >= actual_pointer_ms
            >= selection_input_performance_ms
            >= 0
            and publication_timestamp_us == int(selection_ack["reducer_timestamp_us"])
            and int(actual_pointer.get("button", -1)) == 0
            and int(actual_pointer.get("expectedSequence", -1)) == target_ack_before + 1
            and abs(actual_pointer_x - selected_point[0]) <= 1.0
            and abs(actual_pointer_y - selected_point[1]) <= 1.0
        ), "Selected target ACK was not observed at its first browser publication"
        # The reducer receipt necessarily follows the capture-phase canvas
        # mousedown. Its page-clock age therefore covers all input-to-receipt
        # processing. The Python command round trip conservatively bridges the
        # page sample to the Python response receipt. The earlier pre-mouse
        # marker remains diagnostic only; it is never a clock anchor.
        ack_age_us = round((browser_ticks_ms - publication_ticks_ms) * 1000)
        premouse_input_age_us = round((browser_ticks_ms - selection_input_performance_ms) * 1000)
        actual_input_age_us = round((browser_ticks_ms - actual_pointer_ms) * 1000)
        response_bridge_us = math.ceil(
            (projection_received_at - projection_requested_at) * 1_000_000
        )
        unsafe_publication_anchor_us = publication_timestamp_us + ack_age_us + response_bridge_us
        clock_anchor_server_us = publication_timestamp_us + actual_input_age_us + response_bridge_us
        clock_anchor_monotonic = projection_received_at
        first_ack_before = int(timing_projection.get("attack_ack", {}).get("sequence", 0))
        evidence.setdefault("stage_clock_bridges", []).append(
            {
                "attempt": attempt,
                "selection_reducer_timestamp_us": publication_timestamp_us,
                "publication_performance_ms": publication_ticks_ms,
                "projection_performance_ms": browser_ticks_ms,
                "measured_ACK_age_ms": round(ack_age_us / 1000, 3),
                "measured_input_to_ACK_publication_ms": round(
                    publication_ticks_ms - actual_pointer_ms, 3
                ),
                "premouse_input_performance_ms": selection_input_performance_ms,
                "actual_canvas_mousedown_performance_ms": actual_pointer_ms,
                "premouse_input_age_ms": round(premouse_input_age_us / 1000, 3),
                "actual_input_age_ms": round(actual_input_age_us / 1000, 3),
                "python_response_bridge_us": response_bridge_us,
                "superseded_publication_based_estimated_server_time_us": (
                    unsafe_publication_anchor_us
                ),
                "superseded_estimate_limit": (
                    "unsafe: omits reducer-receipt-to-ACK-publication latency"
                ),
                "target_ACK_republications": int(
                    timing_projection.get("target_ack_republications", 0)
                ),
                "estimated_server_time_us": clock_anchor_server_us,
                "attack_ACK_sequence_baseline": first_ack_before,
            }
        )
        locked = poll(attack_lock, 8)
        state = attack_lock_state if locked else web_stage_state()
        first_lock_clock = estimated_server_time_us()
        a = _monster(state, 1)
        b = _monster(state, 2)
        attempt_evidence = {
            "attempt": attempt,
            "projection_source": "immediate_web_subscription_history",
            "projection_observed_performance_ms": state.get("observed_performance_ms"),
            "expected_lives": {target_id: initial_lives[target_id] for target_id in (1, 2)},
            "history_clock_us": first_lock_clock,
            "locked": locked,
            "A": {
                key: a.get(key)
                for key in (
                    "health",
                    "activity",
                    "action_ends_at_us",
                    "x",
                    "z",
                )
            },
            "B": {
                key: b.get(key)
                for key in (
                    "health",
                    "activity",
                    "action_ends_at_us",
                    "x",
                    "z",
                )
            },
            "succeeded": False,
        }
        if not locked:
            attempt_evidence["latest_web_attack_lock_candidate"] = latest_attack_lock_candidate
            attempt_evidence["best_web_attack_lock_candidate"] = best_attack_lock_candidate
        if locked:
            assert attack_lock_whiff is not None
            whiff = attack_lock_whiff.copy()
            critical_whiff = whiff
            # The authoritative move_to naturally enters idle on arrival. Poll
            # the immediate Web subscription projection directly so no large
            # snapshot read or redundant stop reducer consumes the remaining
            # monster lock.
            web_command("target", x=whiff[0], z=whiff[1])
            staged = poll(whiff_stable, 1.0)
            attempt_evidence["whiff_xz"] = whiff
            attempt_evidence["retreat_travel_m"] = attack_lock_travel_m
            attempt_evidence["required_initial_remaining_us"] = attack_lock_required_us
            attempt_evidence["observed_initial_remaining_us"] = (
                int(a["action_ends_at_us"]) - first_lock_clock
            )
            attempt_evidence["succeeded"] = staged
        stage_attempts.append(attempt_evidence)
        if staged:
            break
        move(
            "web",
            web_id,
            WEB_SAFE,
            f"finisher_failed_stage_attempt_{attempt}_returns_outside_chase",
        )
        stable_since = None
        wait(
            f"finisher_failed_stage_attempt_{attempt}_restores_three_dogs",
            fixture_stable,
            16,
        )
    evidence["stage_attempts"] = stage_attempts
    assert staged, "Three ordinary-input attempts could not retain the reviewed whiff geometry"
    whiff_state = last_whiff_state
    whiff_clock = last_whiff_clock_us
    assert whiff_clock > 0 and last_whiff_observed_at > 0
    assert equipment_center is not None and close_center is not None

    # Send immediately from the accepted whiff state. All reporting and the
    # already-proven staging check run after the typed server receipt is saved.
    set_phase("four_step_chain")
    first_input_sent_at = time.monotonic()
    press_space()
    first_ack = wait_attack_ack(first_ack_before, True, "finisher_combo_1_is_accepted")
    first_ack_observed_at = time.monotonic()
    evidence["first_attack_ack"] = first_ack
    first = first_ack.get("public_action", {}).copy()
    first_receipt_lock_remaining_us = int(_monster(whiff_state, 1)["action_ends_at_us"]) - int(
        first_ack["reducer_timestamp_us"]
    )
    evidence["whiff_attack_lock"] = {
        "history_clock_us": whiff_clock,
        "A_remaining_us": int(_monster(whiff_state, 1)["action_ends_at_us"]) - whiff_clock,
        "required_actual_remaining_us": 350_000,
        "target_ACK_clock_lag_allowance_us": 50_000,
        "actor_xz": _authoritative_xz(whiff_state, web_id),
        "A_xz": _finite([_monster(whiff_state, 1)["x"], _monster(whiff_state, 1)["z"]], 2),
        "B_xz": _finite([_monster(whiff_state, 2)["x"], _monster(whiff_state, 2)["z"]], 2),
        "observed_to_input_ms": round((first_input_sent_at - last_whiff_observed_at) * 1000, 3),
        "input_to_ACK_observed_ms": round((first_ack_observed_at - first_input_sent_at) * 1000, 3),
        "A_remaining_at_server_receipt_us": first_receipt_lock_remaining_us,
    }
    wait(
        "finisher_first_whiff_keeps_350ms_attack_lock_margin",
        lambda: staged,
        0.5,
        TIMING_POLL_SECONDS,
    )
    assert (
        first.get("attack_action_id") == COMBO_1
        and int(first.get("attack_sequence", -1)) > 0
        and int(first.get("action_ends_at_us", 0)) - int(first.get("action_started_at_us", 0))
        == COMBO_DURATIONS_US[COMBO_1]
    )
    evidence["first_receipt_attack_lock_remaining_us"] = first_receipt_lock_remaining_us
    assert first_receipt_lock_remaining_us >= 315_385, (
        "A's accepted attack lock must cover combo1's complete authoritative hit window"
    )
    ack_2, second = send_followup(first, first_ack, COMBO_1)
    ack_3, third = send_followup(second, ack_2, COMBO_2)
    ack_4, fourth = send_followup(third, ack_3, COMBO_3)
    assert (
        int(fourth["action_ends_at_us"]) - int(fourth["action_started_at_us"])
        == (COMBO_DURATIONS_US[COMBO_4])
    )

    reject_before = int(ack_4["sequence"])
    press_space()
    fifth_ack = wait_attack_ack(reject_before, False, "finisher_terminal_fifth_input_is_rejected")
    clear_sent_at = time.monotonic()
    page.mouse.click(*close_center)
    unequip_sent_at = unequip_fast(equipment_center)
    evidence["pre_area_mutations"] = {
        "fifth_ack": fifth_ack,
        "clear_sent_elapsed_seconds": round(clear_sent_at - started, 3),
        "unequip_sent_elapsed_seconds": round(unequip_sent_at - started, 3),
    }

    set_phase("area_and_reaction")
    reaction_states: dict[str, dict] = {}

    def reaction_visible() -> bool:
        local, peer = web(), desktop()
        a_local, b_local, c_local = (_monster(local, target_id) for target_id in (1, 2, 3))
        a_peer, b_peer, c_peer = (_monster(peer, target_id) for target_id in (1, 2, 3))
        local_render = _presentation(local, 2)
        peer_render = _presentation(peer, 2)
        valid = (
            int(a_local.get("health", -1)) == int(a_peer.get("health", -1)) == 0
            and int(b_local.get("health", -1)) == int(b_peer.get("health", -1)) == 65
            and int(c_local.get("health", -1)) == int(c_peer.get("health", -1)) == 100
            and b_local.get("attack_action_id") == b_peer.get("attack_action_id") == FRONT_KNOCKDOWN
            and local_render.get("action_id") == peer_render.get("action_id") == FRONT_KNOCKDOWN
            and int(local_render.get("attack_sequence", -1))
            == int(peer_render.get("attack_sequence", -2))
            and not local.get("combat_target")
            and not bool(sword(local).get("equipped"))
        )
        if valid:
            reaction_states.update({"web": local, "native": peer})
        return valid

    wait("finisher_area_and_front_knockdown_render_on_both_clients", reaction_visible, 3)

    a_life, b_life, c_life = (initial_lives[target_id] for target_id in (1, 2, 3))
    b_start_rows: dict[str, dict] = {}
    for side, snapshot in reaction_states.items():
        rows = [
            row
            for row in _monster_history(snapshot, 2, b_life)
            if row.get("attack_action_id") == FRONT_KNOCKDOWN and int(row.get("health", -1)) == 65
        ]
        assert rows, "Each client must retain B's exact reaction-start public row"
        b_start_rows[side] = rows[0]
        assert int(rows[0]["action_ends_at_us"]) - int(rows[0]["action_started_at_us"]) == 1_166_667

    force_progress_states: dict[str, dict] = {}
    force_candidates: list[dict] = []
    evidence["force_render_candidates"] = force_candidates

    def force_progress_renders() -> bool:
        local, peer = web(), desktop()
        for side, snapshot in (("web", local), ("native", peer)):
            candidate = _force_render_observation(snapshot, b_start_rows[side])
            force_candidates.append({"side": side, **candidate})
            if candidate["valid"] and side not in force_progress_states:
                force_progress_states[side] = candidate
        del force_candidates[:-24]
        return len(force_progress_states) == 2

    wait("finisher_authoritative_force_progress_renders_on_both_clients", force_progress_renders, 2)
    evidence["rendered_force_progress"] = force_progress_states
    # Measure the short force interval before image encoding or file polling.
    native_command("capture")
    page.screenshot(path=str(output / "finisher-front-knockdown.png"))

    wave_states: dict[str, object] = {}

    def screen_wave_evidence_ready() -> bool:
        browser_rows = [
            row
            for row in wave_history_web()
            if isinstance(row, dict)
            and row.get("action_id") == COMBO_4
            and int(row.get("attack_sequence", -1)) == int(fourth["attack_sequence"])
            and row.get("active") is True
        ]
        native = desktop()
        native_rows = [
            row
            for row in native.get("screen_wave_history", [])
            if isinstance(row, dict)
            and row.get("action_id") == COMBO_4
            and row.get("active") is True
        ]
        if not browser_rows:
            return False
        wave_states.update({"browser": browser_rows, "native": native.get("screen_wave", {})})
        return not native_rows

    wait(
        "finisher_in_range_browser_wave_and_out_of_range_native_viewer",
        screen_wave_evidence_ready,
        3,
    )
    applied_wave_rows = []
    for row in wave_states["browser"]:
        offset = _finite(row.get("offset"), 3)
        camera = _finite(row.get("camera_local_position"), 3)
        base = _finite(row.get("base_camera_local_position"), 3)
        assert (
            offset is not None
            and camera is not None
            and base is not None
            and max(abs(value) for value in offset) <= 0.1495 + 0.000001
            and max(abs(camera[index] - base[index]) for index in range(3)) <= 0.1495 + 0.00001
            and row.get("policy") == "deterministic-zero-mean-60hz-v1"
            and int(row.get("activation_us", 0)) == int(fourth["action_started_at_us"]) + 633_334
            and int(row.get("duration_us", 0)) == 200_000
        ), f"Invalid bounded wave/camera observation: {row}"
        # A network callback can activate/synchronize the wave after this frame's
        # camera process. Retain that observation, but only claim application
        # when the actual camera transform agrees with the event's sample.
        if max(abs(camera[index] - base[index] - offset[index]) for index in range(3)) <= 0.00001:
            applied_wave_rows.append(row)
    assert len({int(row["sample_index"]) for row in applied_wave_rows}) >= 2, (
        "At least two distinct wave samples must reach the actual camera transform"
    )
    wave_states["applied_browser_samples"] = applied_wave_rows
    assert int(wave_states["native"].get("trigger_count", -1)) == native_wave_baseline
    assert wave_states["native"].get("last_outcome") == "out_of_range"

    standup_states: dict[str, dict] = {}

    def standup_visible() -> bool:
        local, peer = web(), desktop()
        local_row, peer_row = _monster(local, 2), _monster(peer, 2)
        local_render, peer_render = _presentation(local, 2), _presentation(peer, 2)
        valid = (
            local_row.get("attack_action_id") == peer_row.get("attack_action_id") == FRONT_STANDUP
            and int(local_row.get("attack_sequence", -1))
            == int(peer_row.get("attack_sequence", -2))
            and local_render.get("action_id") == peer_render.get("action_id") == FRONT_STANDUP
        )
        # Force has ended before standup. Both actual renderers must now converge
        # tightly to the subscribed endpoint; the moving-lag allowance ends here.
        for snapshot, row in ((local, local_row), (peer, peer_row)):
            position = _public_xyz(row)
            rendered = _rendered_xz(snapshot, "rendered_monsters", "row_id", 2)
            valid = (
                valid
                and int(row.get("life_sequence", -1)) == b_life
                and position is not None
                and rendered is not None
                and math.dist(rendered, [position[0], position[2]]) <= RENDER_TOLERANCE_M
            )
        if valid:
            standup_states.update({"web": local, "native": peer})
        return valid

    wait("finisher_separate_front_standup_renders_on_both_clients", standup_visible, 3)
    wait(
        "finisher_native_front_knockdown_capture_saved", lambda: (output / "desktop.png").is_file()
    )
    (output / "desktop.png").replace(output / "finisher-native-front-knockdown.png")
    standup_row = _monster(standup_states["web"], 2)
    assert (
        int(standup_row["action_ends_at_us"]) - int(standup_row["action_started_at_us"])
        == 1_000_000
        and int(standup_row["attack_sequence"]) == int(b_start_rows["web"]["attack_sequence"]) + 1
    )

    terminal_state: dict = {}

    def terminal_ready() -> bool:
        nonlocal terminal_state
        state = web()
        row = _player(state, web_id)
        if (
            int(row.get("activity", -1)) != 0
            or row.get("attack_action_id") != COMBO_4
            or int(row.get("attack_sequence", -1)) != int(fourth["attack_sequence"])
        ):
            return False
        terminal_state = state
        return True

    wait("finisher_combo4_root_finishes_after_target_and_equipment_mutation", terminal_ready, 4)
    fourth_start = _public_xyz(fourth)
    terminal_position = _public_xyz(_player(terminal_state, web_id))
    assert fourth_start is not None and terminal_position is not None
    heading = float(fourth["heading"])
    forward = _forward(heading)
    delta = [terminal_position[0] - fourth_start[0], terminal_position[2] - fourth_start[2]]
    along = delta[0] * forward[0] + delta[1] * forward[1]
    cross = abs(delta[0] * forward[1] - delta[1] * forward[0])
    assert abs(along - COMBO_4_ROOT_M) <= ROOT_TOLERANCE_M and cross <= ROOT_TOLERANCE_M
    wait(
        "finisher_combo4_terminal_position_converges_on_both_renderers",
        lambda: (
            (local := _rendered_xz(web(), "rendered_actors", "identity", web_id)) is not None
            and (peer := _rendered_xz(desktop(), "rendered_actors", "identity", web_id)) is not None
            and math.dist(local, [terminal_position[0], terminal_position[2]]) <= RENDER_TOLERANCE_M
            and math.dist(peer, [terminal_position[0], terminal_position[2]]) <= RENDER_TOLERANCE_M
        ),
        3,
    )

    histories: dict[str, object] = {}
    expected_actions = (COMBO_1, COMBO_2, COMBO_3, COMBO_4)
    first_sequence = int(first["attack_sequence"])
    for side, snapshot in (("web", web()), ("native", desktop())):
        action_rows: dict[str, list[dict]] = {}
        for index, action_id in enumerate(expected_actions):
            rows = _player_history(snapshot, web_id, action_id, first_sequence + index)
            assert rows, f"{side} retained no authoritative {action_id} history"
            assert any(
                isinstance(entry.get("presentation"), dict)
                and entry["presentation"].get("action_id") == action_id
                and int(entry["presentation"].get("attack_sequence", -1)) == first_sequence + index
                for entry in rows
            ), f"{side} retained no rendered {action_id} presentation"
            headings = [float(entry["public_action"]["heading"]) for entry in rows]
            assert max(abs(value - headings[0]) for value in headings) <= 0.000001
            valid_local_transforms = 0
            for entry in rows:
                presentation = entry.get("presentation", {})
                local = _finite(presentation.get("presentation_local_position"), 3)
                model = _finite(presentation.get("model_local_position"), 3)
                if local is not None and model is not None:
                    valid_local_transforms += 1
                    assert max(abs(value) for value in [*local, *model]) <= 0.001
            assert valid_local_transforms > 0, (
                f"{side} retained no finite local/model transform for {action_id}"
            )
            action_rows[action_id] = rows
        a_health = _health_history(snapshot, 1, a_life)
        assert a_health == [100, 65, 30, 0]
        assert a_health[:2] == [100, 65], (
            f"{side} must retain A at 100 through the staged combo1 miss before combo2 damage"
        )
        assert _health_history(snapshot, 2, b_life) == [100, 65]
        assert _health_history(snapshot, 3, c_life) == [100]
        b_rows = _monster_history(snapshot, 2, b_life)
        start = _public_xyz(b_start_rows[side])
        assert start is not None
        reaction_sequence = int(b_start_rows[side]["attack_sequence"])
        reaction_started_at_us = int(b_start_rows[side]["action_started_at_us"])
        force_rows = [
            row
            for row in b_rows
            if int(row.get("attack_sequence", -1)) == reaction_sequence
            and int(row.get("action_started_at_us", -1)) == reaction_started_at_us
            and row.get("attack_action_id") == FRONT_KNOCKDOWN
        ]
        assert force_rows, f"{side} retained no exact accepted B reaction/force rows"
        force_distance = max(math.dist(start, _public_xyz(row)) for row in force_rows)
        assert FORCE_DISTANCE_M - 0.003 <= force_distance <= FORCE_DISTANCE_M + 0.003
        assert not any(row.get("attack_action_id") == BACK_KNOCKDOWN for row in b_rows)
        histories[side] = {
            "actions": action_rows,
            "B": b_rows,
            "B_force_rows": force_rows,
            "force_distance_m": force_distance,
        }
    evidence["histories"] = histories

    set_phase("ordinary_cleanup")
    move("web", web_id, WEB_SAFE, "finisher_browser_releases_survivor_chase")
    # Read the server-selected bag cell after unequip, then finish damaged B
    # through ordinary attacks. Its original pre-test slot may be on page two.
    equip()

    def b_home_ready() -> bool:
        state = web()
        b = _monster(state, 2)
        return (
            int(b.get("life_sequence", -1)) == b_life
            and int(b.get("health", -1)) == 65
            and int(b.get("activity", -1)) == 0
            and math.dist([float(b["x"]), float(b["z"])], DOG_HOMES[2]) < 0.15
        )

    wait("finisher_damaged_B_returns_home_for_cleanup", b_home_ready, 8)
    move("web", web_id, DOG_HOMES[2], "finisher_browser_approaches_damaged_B", 8)
    b_state: dict = {}
    b_point: list[float] | None = None

    def b_pick_ready() -> bool:
        nonlocal b_state, b_point
        b_state = web()
        b_point = _pick(b_state, 2, b_life)
        return b_point is not None

    wait("finisher_cleanup_B_exact_life_pick_is_rendered", b_pick_ready, 3)
    assert b_point is not None
    cleanup_target_ack_before = int(last_target_ack().get("sequence", 0))
    page.mouse.click(*b_point)
    cleanup_target_ack = wait_target_ack(cleanup_target_ack_before, 2, b_life)
    evidence["cleanup_B_selection_ack"] = cleanup_target_ack
    cleanup_ack_before = int(last_attack_ack().get("sequence", 0))
    press_space()
    cleanup_first_ack = wait_attack_ack(
        cleanup_ack_before, True, "finisher_cleanup_first_attack_is_accepted"
    )
    cleanup_first = cleanup_first_ack["public_action"]
    _, cleanup_second = send_followup(cleanup_first, cleanup_first_ack, COMBO_1)
    wait(
        "finisher_cleanup_two_ordinary_hits_defeat_only_B",
        lambda: (
            int(_monster(web(), 2).get("health", -1)) == 0
            and int(_monster(desktop(), 2).get("health", -1)) == 0
            and int(_monster(web(), 3).get("health", -1)) == 100
            and cleanup_second.get("attack_action_id") == COMBO_2
        ),
        4,
    )
    restore_inventory()
    move("web", web_id, WEB_SAFE, "finisher_browser_returns_outside_chase")

    def restored_fixture() -> bool:
        local, peer = web(), desktop()
        return all(
            int(_monster(local, target_id).get("life_sequence", -1))
            == int(_monster(peer, target_id).get("life_sequence", -2))
            == initial_lives[target_id] + (1 if target_id in (1, 2) else 0)
            and int(_monster(local, target_id).get("health", -1)) == DOG_MAX_HEALTH
            and int(_monster(local, target_id).get("activity", -1)) == 0
            and math.dist(
                [float(_monster(local, target_id)["x"]), float(_monster(local, target_id)["z"])],
                home,
            )
            < 0.15
            for target_id, home in DOG_HOMES.items()
        )

    wait("finisher_A_and_B_respawn_while_C_remains_untouched", restored_fixture, 20)
    final_web, final_native = web(), desktop()
    return {
        "definition_hash": DEFINITION_HASH,
        "initial_lives": initial_lives,
        "first_ack": first_ack,
        "combo4_ack": ack_4,
        "combo4": fourth,
        "terminal": _player(terminal_state, web_id),
        "screen_wave": wave_states,
        "reactions": {
            "front_knockdown": b_start_rows,
            "front_standup": standup_row,
        },
        "final_web": {target_id: _monster(final_web, target_id) for target_id in DOG_HOMES},
        "final_native": {target_id: _monster(final_native, target_id) for target_id in DOG_HOMES},
        "inventory": sword(final_web),
    }
