"""Exported canvas checks for subscribed actor, action, and equipment presentation."""

WARRIOR_ID = "actor.player.warrior-male"
DOG_ID = "actor.mob.wild-dog-101"
WARRIOR_MODEL = "res://assets/imported/content/p0-warrior-dog/actors/warrior-male.glb"
DOG_MODEL = "res://assets/imported/content/p0-warrior-dog/actors/wild-dog-101.glb"


def rendered_actor(snapshot: dict, identity: str) -> dict:
    return next(
        (
            actor
            for actor in snapshot.get("rendered_actors", [])
            if actor.get("identity") == identity
        ),
        {},
    )


def rendered_dog(snapshot: dict) -> dict:
    return next(
        (
            monster
            for monster in snapshot.get("rendered_monsters", [])
            if monster.get("actor_id") == DOG_ID and monster.get("definition_vnum") == 101
        ),
        {},
    )


def exercise_actors(
    page,
    web,
    desktop,
    web_command,
    wait,
    web_id: str,
    native_id: str,
    output,
) -> dict:
    """Use subscribed rows and visible inventory controls; no privileged state changes."""

    def local_actor() -> dict:
        return rendered_actor(web(), web_id)

    def peer_actor() -> dict:
        return rendered_actor(desktop(), web_id)

    def local_dog() -> dict:
        return rendered_dog(web())

    def peer_dog() -> dict:
        return rendered_dog(desktop())

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

    def dogs_match() -> bool:
        local = local_dog()
        peer = peer_dog()
        return (
            local.get("row_id", 0) > 0
            and peer.get("row_id") == local.get("row_id")
            and local.get("actor_id") == DOG_ID
            and peer.get("actor_id") == DOG_ID
            and local.get("definition_vnum") == 101
            and peer.get("definition_vnum") == 101
            and local.get("model_path") == DOG_MODEL
            and peer.get("model_path") == DOG_MODEL
            and bool(local.get("animation"))
            and peer.get("animation") == local.get("animation")
            and peer.get("action_id") == local.get("action_id")
            and peer.get("attack_sequence") == local.get("attack_sequence")
        )

    wait(
        "generated_warrior_models_render_for_both_peers",
        lambda: all(
            actor.get("actor_id") == WARRIOR_ID
            and actor.get("model_path") == WARRIOR_MODEL
            and actor.get("animation")
            for actor in (
                local_actor(),
                peer_actor(),
                rendered_actor(web(), native_id),
                rendered_actor(desktop(), native_id),
            )
        ),
    )
    wait(
        "original_wild_dog_subscription_matches_both_clients",
        dogs_match,
        60,
    )
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

    def onehand_action_matches() -> bool:
        local = local_actor()
        peer = peer_actor()
        return (
            local.get("attack_sequence", 0) > attack_before
            and peer.get("attack_sequence") == local.get("attack_sequence")
            and local.get("action_id") == "actor.player.warrior-male.onehand.combo_1"
            and peer.get("action_id") == local.get("action_id")
            and local.get("mode") == "onehand"
            and peer.get("mode") == "onehand"
            and bool(local.get("animation"))
            and peer.get("animation") == local.get("animation")
            and local.get("weapon_vnum") == 10
            and peer.get("weapon_vnum") == 10
        )

    wait(
        "accepted_onehand_action_projects_to_both_clients",
        onehand_action_matches,
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
        "local": local_actor(),
        "peer": peer_actor(),
        "local_dog": local_dog(),
        "peer_dog": peer_dog(),
    }
