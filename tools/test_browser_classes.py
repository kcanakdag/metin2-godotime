"""Rendered original class creation and ordinary equipment/attack input checks."""

from test_browser_actors import rendered_actor


def exercise_previews(page, account, click, wait, output):
    snapshots = []
    for class_id, name in enumerate(("warrior", "ninja", "sura", "shaman")):
        for sex in (0, 1):
            click("male" if sex == 0 else "female")
            actor = f"actor.player.{name}-{'male' if sex == 0 else 'female'}"
            wait(
                f"browser_preview_{name}_{sex}",
                lambda class_id=class_id, sex=sex, actor=actor: (
                    account().get("character_class") == class_id
                    and account().get("sex") == sex
                    and account()["preview"]["models"] == 4
                    and account()["preview"]["actors"].get(f"CharacterSlot{class_id}") == actor
                    and all(
                        motion["mode"] == "intro" and motion["action_id"].endswith(".intro.wait")
                        for motion in account()["preview"]["motions"].values()
                    )
                    and account()["preview"]["camera_facing"]
                    and not account()["preview"]["error"]
                ),
            )
            page.screenshot(path=str(output / f"class-{name}-{sex}.png"))
            snapshots.append(account()["preview"])
        click("slot_next")
    click("slot_next")
    wait(
        "browser_selects_female_ninja_for_creation",
        lambda: account().get("character_class") == 1 and account().get("sex") == 1,
    )
    return snapshots


def exercise_class_world(
    page,
    web,
    desktop,
    wait,
    identity,
    actor_id,
    output,
    *,
    weapon_vnum=0,
    mode="general",
    camera_wave=False,
):
    def local():
        return rendered_actor(web(), identity)

    def peer():
        return rendered_actor(desktop(), identity)

    label = actor_id.removeprefix("actor.player.")
    wait(
        f"{label}_renders_same_original_model_on_web_and_linux",
        lambda: all(
            row.get("actor_id") == actor_id
            and row.get("model_path") == f"res://assets/imported/characters/actors/{label}.glb"
            and row.get("animation")
            and not row.get("error")
            for row in (local(), peer())
        ),
    )
    page.keyboard.press("c")
    wait(f"{label}_status_opens", lambda: web()["ui"]["status"]["visible"])
    page.screenshot(path=str(output / f"{label}-status.png"))
    page.keyboard.press("Escape")
    wait(f"{label}_status_closes", lambda: not web()["ui"]["status"]["visible"])
    if weapon_vnum:
        page.keyboard.press("i")
        wait(f"{label}_inventory_opens", lambda: web()["ui"]["visible"])
        item = next(row for row in web()["inventory"] if row["vnum"] == weapon_vnum)
        cell = int(item["cell"])
        origin = web()["ui"]["grid_origin"]
        page.mouse.click(
            origin[0] + cell % 5 * 32 + 16, origin[1] + cell // 5 * 32 + 16, button="right"
        )
        wait(
            f"{label}_weapon_attaches_for_both_players",
            lambda: all(
                row.get("equipment_attached")
                and row.get("weapon_vnum") == weapon_vnum
                and row.get("mode") == mode
                for row in (local(), peer())
            ),
        )
        page.keyboard.press("Escape")
        wait(f"{label}_inventory_closes", lambda: not web()["ui"]["visible"])
    before = local()["attack_sequence"]
    wave_before = int(web().get("screen_wave", {}).get("trigger_count", 0))
    expected = actor_id + (f".{mode}.combo_1" if weapon_vnum else ".general.normal_attack")

    def matching_attack():
        # Each read crosses a process boundary. Re-reading midway through the
        # predicate can compare different steps of a short, healthy combo.
        current, remote = local(), peer()
        return (
            current.get("attack_sequence", 0) > before
            and remote.get("attack_sequence") == current.get("attack_sequence")
            and current.get("action_id", "").startswith(expected)
            and remote.get("action_id") == current.get("action_id")
            and bool(current.get("animation"))
            and remote.get("animation") == current.get("animation")
        )

    page.keyboard.down("Space")
    try:
        wait(
            f"{label}_keyboard_attack_plays_for_both_players",
            matching_attack,
            5,
            poll_interval=0.03,
        )
        if weapon_vnum:
            for step in range(2, 5):
                action = actor_id + f".{mode}.combo_{step}"
                wait(
                    f"{label}_held_space_reaches_step_{step}_on_both_clients",
                    lambda action=action: all(
                        row.get("action_id") == action and bool(row.get("animation"))
                        for row in (local(), peer())
                    ),
                    5,
                    poll_interval=0.02,
                )
        else:
            wait(
                f"{label}_held_space_repeats_unarmed_attack_on_both_clients",
                lambda: (
                    local().get("attack_sequence", 0) >= before + 2
                    and peer().get("attack_sequence") == local().get("attack_sequence")
                    and local().get("action_id", "").startswith(expected)
                    and peer().get("action_id") == local().get("action_id")
                ),
                5,
                poll_interval=0.03,
            )
    finally:
        page.keyboard.up("Space")
    if camera_wave:
        wait(
            f"{label}_authored_finisher_triggers_camera_wave",
            lambda: int(web().get("screen_wave", {}).get("trigger_count", 0)) > wave_before,
            5,
            poll_interval=0.02,
        )
    sample = {"local": local(), "peer": peer(), "screen_wave": web().get("screen_wave", {})}
    page.screenshot(path=str(output / f"{label}-attack.png"))
    wait(
        f"{label}_returns_to_idle",
        lambda: (
            local()
            .get("action_id", "")
            .startswith(actor_id + (f".{mode}.wait" if weapon_vnum else ".general.wait"))
        ),
        5,
    )
    return sample
