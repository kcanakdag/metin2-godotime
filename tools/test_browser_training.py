"""Exercise an authored practice target in real exported Web and Linux clients."""

from __future__ import annotations

from test_browser_target import _pick, _player, _presentation


def exercise_training_dummy(page, web, desktop, command, wait, identity, output):
    def dummy(snapshot):
        return next((m for m in snapshot.get("monsters", []) if m.get("id") == 900001), {})

    wait(
        "training_dummy_subscribed_in_both_exports", lambda: bool(dummy(web()) and dummy(desktop()))
    )
    start = _player(web(), identity)
    target = dummy(web())
    life, health = int(target["life_sequence"]), int(target["health"])
    wait(
        "training_dummy_model_in_both_exports",
        lambda: all(
            _presentation(snapshot(), 900001).get("actor_id") == "actor.training.straw-dummy"
            and _presentation(snapshot(), 900001).get("clip") == "wait"
            and not _presentation(snapshot(), 900001).get("error")
            for snapshot in (web, desktop)
        ),
    )
    destination = [float(target["x"]) - 1.0, float(target["z"])]
    command("target", x=destination[0], z=destination[1])

    def near_target():
        actor = _player(desktop(), identity)
        return (
            bool(actor)
            and ((actor["x"] - destination[0]) ** 2 + (actor["z"] - destination[1]) ** 2) < 0.04
        )

    wait("training_dummy_approach_replicates", near_target)
    command("stop")
    wait(
        "training_dummy_has_visible_pick_projection", lambda: _pick(web(), 900001, life) is not None
    )
    point = _pick(web(), 900001, life)
    page.mouse.click(*point)
    wait(
        "training_dummy_pointer_selects_exact_life",
        lambda: web().get("combat_target", {}).get("target_id") == 900001,
    )
    page.keyboard.down("Space")
    try:
        wait(
            "training_dummy_browser_damage_reaches_both_clients",
            lambda: (
                int(dummy(desktop()).get("health", health)) < health
                and dummy(web()).get("health") == dummy(desktop()).get("health")
            ),
            12,
        )
    finally:
        page.keyboard.up("Space")
    page.screenshot(path=str(output / "training-dummy-browser.png"))
    after = dummy(desktop())
    wait(
        "training_dummy_remains_anchored_in_export",
        lambda: dummy(web()).get("x") == target["x"] and dummy(web()).get("z") == target["z"],
    )
    command("target", x=start["x"], z=start["z"])
    return {"before": target, "after": after, "pointer": point, "life": life}
