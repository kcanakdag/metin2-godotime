"""Exported canvas checks for subscribed actor, action, and equipment presentation."""

import json
from functools import lru_cache
from pathlib import Path

WARRIOR_ID = "actor.player.warrior-male"
WARRIOR_ONEHAND_COMBO = "actor.player.warrior-male.onehand.combo_1"

ROOT = Path(__file__).resolve().parents[1]
CHARACTER_CATALOG = ROOT / "client/assets/imported/characters/catalog.v1.json"
MOB_PRESENTATION = ROOT / "client/assets/imported/mobs/presentation.v1.json"


@lru_cache(maxsize=None)
def actor_models() -> dict[str, str]:
    """Map every installed actor id to its compiled model path.

    Expectations come from the generated content the exports are built from,
    so a relocated character model or a newly installed species does not leave
    the harness asserting a retired resource path or a fixture-only mob id.
    """

    models: dict[str, str] = {}
    for catalog in (CHARACTER_CATALOG, MOB_PRESENTATION):
        if not catalog.is_file():
            raise RuntimeError(
                f"{catalog} is missing; build the client content before running the "
                "actor acceptance"
            )
        for actor in json.loads(catalog.read_text()).get("actors", []):
            actor_id = actor.get("id")
            path = (actor.get("model") or {}).get("path")
            if isinstance(actor_id, str) and isinstance(path, str) and path:
                models[actor_id] = path
    if WARRIOR_ID not in models:
        raise RuntimeError(f"{CHARACTER_CATALOG} does not list {WARRIOR_ID}")
    return models


def warrior_model() -> str:
    return actor_models()[WARRIOR_ID]


def rendered_actor(snapshot: dict, identity: str) -> dict:
    return next(
        (
            actor
            for actor in snapshot.get("rendered_actors", [])
            if actor.get("identity") == identity
        ),
        {},
    )


def rendered_catalog_mob(snapshot: dict) -> dict:
    """First rendered monster that the installed mob catalog recognizes."""

    models = actor_models()
    return next(
        (
            monster
            for monster in snapshot.get("rendered_monsters", [])
            if monster.get("actor_id") in models
        ),
        {},
    )


def captured_catalog_mobs(field_mobs) -> tuple[dict, dict]:
    """Lowest shared field-route monster captured from both exported clients."""

    if not isinstance(field_mobs, dict):
        return {}, {}
    web_rows = field_mobs.get("web_mobs") or {}
    native_rows = field_mobs.get("native_mobs") or {}
    models = actor_models()
    for row_id in sorted(set(web_rows) & set(native_rows), key=int):
        row = web_rows[row_id]
        if row.get("actor_id") in models:
            return row, native_rows[row_id]
    return {}, {}


def catalog_mob_pair_matches(web_row: dict, native_row: dict) -> bool:
    """Both peers project the same species, model, animation and action."""

    actor_id = web_row.get("actor_id")
    if not actor_id or actor_id != native_row.get("actor_id"):
        return False
    if actor_id not in actor_models():
        return False
    vnum = int(web_row.get("definition_vnum") or 0)
    if vnum <= 0 or vnum != int(native_row.get("definition_vnum") or 0):
        return False
    expected_model = actor_models()[actor_id]
    if (
        web_row.get("model_path") != expected_model
        or native_row.get("model_path") != expected_model
    ):
        return False
    if not web_row.get("animation") or native_row.get("animation") != web_row.get("animation"):
        return False
    return bool(web_row.get("action_id")) and native_row.get("action_id") == web_row.get(
        "action_id"
    )


def accepted_onehand_entry(history, identity: str, above_sequence: int) -> dict:
    """First server-accepted onehand attack recorded in a client's history.

    The history is a rolling record of the subscribed public action rows, so it
    keeps an accepted action after the transient combo clip has finished. The
    exported Web build runs at a few frames per second under software
    rendering, which can step straight over a one-second clip; a check that
    required the live presentation to still be the clip would fail on the
    renderer's frame rate rather than on the game.
    """

    if not isinstance(history, list):
        return {}
    for entry in history:
        if not isinstance(entry, dict) or entry.get("identity") != identity:
            continue
        action = entry.get("public_action") or {}
        if int(action.get("attack_sequence") or 0) <= above_sequence:
            continue
        if action.get("attack_action_id") == WARRIOR_ONEHAND_COMBO:
            return entry
    return {}


def presentation_played(history, identity: str, action_id: str) -> bool:
    """Whether a client's own history shows it rendered the given action."""

    if not isinstance(history, list):
        return False
    for entry in history:
        if not isinstance(entry, dict) or entry.get("identity") != identity:
            continue
        if (entry.get("presentation") or {}).get("action_id") == action_id:
            return True
    return False


def exercise_actors(
    page,
    web,
    desktop,
    web_command,
    wait,
    web_id: str,
    native_id: str,
    output,
    field_mobs=None,
) -> dict:
    """Use subscribed rows and visible inventory controls; no privileged state changes."""

    expected_warrior_model = warrior_model()

    def local_actor() -> dict:
        return rendered_actor(web(), web_id)

    def peer_actor() -> dict:
        return rendered_actor(desktop(), web_id)

    def sword() -> dict:
        return next(row for row in web()["inventory"] if row["vnum"] == 10)

    def ui() -> dict:
        return web()["ui"]

    def cell_point(cell: int) -> list[float]:
        origin = ui()["grid_origin"]
        return [origin[0] + (cell % 5) * 32 + 16, origin[1] + (cell % 45 // 5) * 32 + 16]

    def drag(start: list[float], end: list[float]) -> None:
        page.mouse.move(*start)
        page.mouse.down()
        page.mouse.move(start[0] + 12, start[1] + 5, steps=5)
        page.mouse.move(*end, steps=20)
        page.mouse.up()

    def show_page(page_index: int, check: str) -> None:
        page.mouse.click(*ui()["tab_centers"][page_index])
        wait(check, lambda: ui()["visible"] and ui()["page"] == page_index)

    wait(
        "generated_warrior_models_render_for_both_peers",
        lambda: all(
            actor.get("actor_id") == WARRIOR_ID
            and actor.get("model_path") == expected_warrior_model
            and actor.get("animation")
            for actor in (
                local_actor(),
                peer_actor(),
                rendered_actor(web(), native_id),
                rendered_actor(desktop(), native_id),
            )
        ),
    )

    def live_mob_pair() -> tuple[dict, dict]:
        return rendered_catalog_mob(web()), rendered_catalog_mob(desktop())

    captured_web, captured_native = captured_catalog_mobs(field_mobs)
    if captured_web:
        if not catalog_mob_pair_matches(captured_web, captured_native):
            raise AssertionError(
                "Field-route mob presentation disagrees between the exports and the "
                f"installed catalog: {captured_web!r} vs {captured_native!r}"
            )
        wait(
            "original_field_mob_presentation_matches_both_clients",
            lambda: True,
        )
        mob_evidence = {"source": "field_route", "web": captured_web, "native": captured_native}
    else:
        wait(
            "original_field_mob_presentation_matches_both_clients",
            lambda: all(live_mob_pair()) and catalog_mob_pair_matches(*live_mob_pair()),
            60,
        )
        mob_evidence = {"source": "live_world", "web": live_mob_pair()[0]}
    assert not local_actor()["equipment_attached"] and not peer_actor()["equipment_attached"]
    wait(
        "browser_receives_sword_for_actor_projection",
        lambda: any(row["vnum"] == 10 for row in web()["inventory"]),
    )
    original_cell = int(sword()["cell"])
    assert 0 <= original_cell < 90 and not sword().get("equipped")
    sword_page = original_cell // 45
    incoming_page = int(ui()["page"])
    page.keyboard.press("i")
    wait("actor_projection_inventory_opens", lambda: ui()["visible"])
    show_page(sword_page, "actor_projection_shows_original_sword_page")
    page.mouse.click(*cell_point(original_cell), button="right")
    wait(
        "equipped_appearance_projects_to_both_clients",
        lambda: (
            sword().get("equipped")
            and local_actor().get("weapon_vnum") == 10
            and local_actor().get("equipment_attached")
            and peer_actor().get("weapon_vnum") == 10
            and peer_actor().get("equipment_attached")
            and local_actor().get("mode") == "onehand"
            and peer_actor().get("mode") == "onehand"
        ),
    )
    page.screenshot(path=str(output / "actors-equipped.png"))
    attack_before = local_actor()["attack_sequence"]
    web_command("attack")
    peer_combo_played: dict[str, bool] = {}

    def onehand_action_matches() -> bool:
        # The native peer's public action history is a short rolling window, so
        # the transient combo presentation can pass through it before the
        # mirrored-action conditions settle. Record the observation while this
        # predicate polls instead of polling for it again afterwards.
        if presentation_played(
            desktop().get("public_action_history"), web_id, WARRIOR_ONEHAND_COMBO
        ):
            peer_combo_played["seen"] = True
        local = local_actor()
        peer = peer_actor()
        return (
            peer_combo_played.get("seen", False)
            and local.get("attack_sequence", 0) > attack_before
            and peer.get("attack_sequence") == local.get("attack_sequence")
            and bool(
                accepted_onehand_entry(web().get("public_action_history"), web_id, attack_before)
            )
            and bool(
                accepted_onehand_entry(
                    desktop().get("public_action_history"), web_id, attack_before
                )
            )
            and local.get("mode") == "onehand"
            and peer.get("mode") == "onehand"
            and bool(local.get("animation"))
            and peer.get("animation") == local.get("animation")
            and local.get("weapon_vnum") == 10
            and peer.get("weapon_vnum") == 10
            and bool(local.get("equipment_attached"))
            and bool(peer.get("equipment_attached"))
        )

    wait(
        "accepted_onehand_action_projects_to_both_clients",
        onehand_action_matches,
    )
    wait(
        "peer_client_rendered_the_accepted_onehand_combo",
        lambda: peer_combo_played.get("seen", False),
        1,
    )
    page.screenshot(path=str(output / "actors-equipped-combo1.png"))
    equipment = ui()["equipment_origin"]
    drag([equipment[0] + 16, equipment[1] + 16], cell_point(original_cell))
    wait(
        "original_sword_cell_and_unequipped_appearance_restore_for_both_clients",
        lambda: (
            not sword().get("equipped")
            and sword().get("cell") == original_cell
            and local_actor().get("weapon_vnum") == 0
            and not local_actor().get("equipment_attached")
            and peer_actor().get("weapon_vnum") == 0
            and not peer_actor().get("equipment_attached")
        ),
    )
    show_page(incoming_page, "actor_projection_restores_incoming_inventory_page")
    page.keyboard.press("Escape")
    wait("actor_projection_inventory_closes", lambda: not ui()["visible"])
    return {
        "expected": {
            "warrior": expected_warrior_model,
            "field_mob": actor_models().get((mob_evidence.get("web") or {}).get("actor_id")),
        },
        "local": local_actor(),
        "peer": peer_actor(),
        "field_mob": mob_evidence,
    }
