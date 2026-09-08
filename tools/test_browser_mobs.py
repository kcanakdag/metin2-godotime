"""Population evidence from the actual exported clients' subscribed snapshots."""

import math
import statistics
import time
from collections import Counter


def population_summary(web, native, catalog):
    expected = {int(mob["vnum"]) for mob in catalog["mobs"]}
    observed = []
    counts = []
    for snapshot in (web, native):
        ids = {}
        for row in snapshot["monsters"]:
            if int(row["id"]) == 900001:  # Independent authored practice dummy.
                continue
            identity, vnum = int(row["id"]), int(row["definition_vnum"])
            assert identity > 900001 and identity not in ids, "Invalid or duplicate mob ID"
            assert vnum in expected, "Unregistered mob species"
            assert all(math.isfinite(row[key]) for key in ("x", "y", "z")), "Invalid mob position"
            ids[identity] = vnum
        assert len(ids) > 2000, "Expected full original Yongan population"
        assert set(ids.values()) == expected, "Original species missing from subscription"
        observed.append(ids)
        counts.append(dict(sorted(Counter(ids.values()).items())))
    assert observed[0] == observed[1], "Exported clients received different mob populations"
    return {"count": len(observed[0]), "species": len(expected), "species_counts": counts[0]}


def exercise_field(
    page,
    web,
    desktop,
    web_command,
    native_command,
    wait,
    route,
    output,
    *,
    return_to_town=True,
    profile_probe=False,
):
    for snapshot in (web(), desktop()):
        assert snapshot["world_info"] == {
            "map_id": route["map_id"],
            "content_hash": route["map_hash"],
        }
    points = route["waypoints"]

    def arrived(snapshot, point):
        position = snapshot.get("server_position", [])
        return len(position) == 3 and math.dist([position[0], position[2]], point) < 0.25

    def walk(waypoints, label):
        for index, point in enumerate(waypoints):
            web_command("target", x=point[0], z=point[1])
            native_command("target", x=point[0], z=point[1])
            wait(
                f"{label}_{index}",
                lambda point=point: arrived(web(), point) and arrived(desktop(), point),
                15,
            )

    walk(points[1:], "field_route_outward")

    def mobs(snapshot):
        return {
            int(row["row_id"]): row
            for row in snapshot.get("monster_presentations", [])
            if row.get("model_path", "").startswith("res://assets/imported/mobs/")
            and row.get("animation")
            and row.get("pick", {}).get("available")
        }

    wait(
        "both_exports_render_original_field_mobs",
        lambda: bool(mobs(web()).keys() & mobs(desktop()).keys()),
        30,
    )
    page.screenshot(path=str(output / "field-mobs-browser.png"))
    native_command("capture")
    wait("field_native_capture_saved", lambda: (output / "desktop.png").is_file())
    (output / "desktop.png").replace(output / "field-mobs-native.png")
    samples = []
    for _ in range(12):
        page.wait_for_timeout(500)
        a, b = web(), desktop()
        samples.append(
            {
                "time": time.monotonic(),
                "web_fps": a["fps"],
                "native_fps": b["fps"],
                "web_rendered": len(a.get("rendered_monsters", [])),
                "web_npcs": len(a.get("rendered_npcs", [])),
                "native_npcs": len(b.get("rendered_npcs", [])),
                "native_rendered": len(b.get("rendered_monsters", [])),
            }
        )
    result = {
        "web_mobs": mobs(web()),
        "native_mobs": mobs(desktop()),
        "samples": samples,
        "instrumented_web_median_fps": statistics.median(s["web_fps"] for s in samples),
    }
    if profile_probe:
        web_command("profile_performance")
        native_command("profile_performance")
        page.wait_for_timeout(6500)
        wait(
            "both_clients_complete_snapshot_free_profile",
            lambda: all(
                state.get("performance_profile", {}).get("duration_us", 0) >= 5_000_000
                and state["performance_profile"].get("frames", 0) > 0
                and state["performance_profile"].get("snapshot_sampling") is False
                for state in (web(), desktop())
            ),
            15,
        )
        result["snapshot_free_profile"] = {
            "web": web()["performance_profile"],
            "native": desktop()["performance_profile"],
        }
    if return_to_town:
        walk(list(reversed(points[:-1])), "field_route_return")
    return result
