"""Actual canvas mouse/keyboard checks for the classic inventory in Web exports."""

import time


def exercise_inventory(page, snapshot, wait, output):
    """Read coordinates/state from the probe; perform every item action through visible UI."""

    def item(vnum):
        return next(row for row in snapshot()["inventory"] if row["vnum"] == vnum)

    def ui():
        return snapshot()["ui"]

    def click(point, **kwargs):
        page.mouse.click(*point, **kwargs)

    def drag(start, end):
        page.mouse.move(*start)
        page.mouse.down()
        page.mouse.move(start[0] + 12, start[1] + 5, steps=5)
        page.mouse.move(*end, steps=20)
        page.mouse.up()

    def cell_point(cell):
        origin = ui()["grid_origin"]
        return [origin[0] + (cell % 5) * 32 + 16, origin[1] + (cell % 45 // 5) * 32 + 16]

    wait("browser_receives_own_starter_items", lambda: len(snapshot().get("inventory", [])) == 2)
    sword, potion = item(10), item(27001)
    page.keyboard.press("i")
    wait("inventory_keyboard_opens_original_window", lambda: ui()["visible"])
    sword_point = cell_point(sword["cell"])
    window = ui()["window_rect"]
    # ClassicSlot exposes its tooltip on the real mouse-enter edge. Enter from
    # outside the newly shown inventory and retain intermediate motion events so
    # opening the window under a previously stationary pointer cannot lose it.
    page.mouse.move(window[0] - 8, sword_point[1])
    page.mouse.move(*sword_point, steps=6)
    wait("original_item_tooltip_appears", lambda: ui()["tooltip_visible"])
    page.screenshot(path=str(output / "inventory-tooltip.png"))
    click(cell_point(sword["cell"]), button="right")
    wait("inventory_right_click_equips_server_item", lambda: item(10)["equipped"])
    weapon = ui()["equipment_origin"]
    drag([weapon[0] + 16, weapon[1] + 16], cell_point(2))
    wait(
        "equipment_drag_unequips_into_bag",
        lambda: not item(10)["equipped"] and item(10)["cell"] == 2,
    )
    drag(cell_point(potion["cell"]), ui()["quickslot_centers"][0])
    wait("potion_drag_binds_quickslot", lambda: ui()["quickslot_bindings"][0] == potion["id"])
    errors_before = len(snapshot().get("errors", []))
    page.keyboard.press("1")
    wait(
        "quickslot_sends_validated_potion_intent", lambda: len(snapshot()["errors"]) > errors_before
    )
    assert item(27001)["count"] == potion["count"], "Rejected potion must not disappear"
    # Original click-to-carry permits changing the bag page while an item is attached.
    click(cell_point(2))
    click(ui()["tab_centers"][1])
    wait("inventory_second_page_opens", lambda: ui()["page"] == 1)
    click(cell_point(45))
    wait("carried_item_moves_between_pages", lambda: item(10)["cell"] == 45)
    page.screenshot(path=str(output / "inventory-page-two.png"))
    # Closing and reopening preserves position, page and confirmed contents.
    window = ui()["window_rect"]
    drag([window[0] + 60, window[1] + 15], [window[0] - 100, window[1] + 30])
    time.sleep(0.3)
    moved = ui()["window_rect"]
    assert moved[0] < window[0] - 80, "Inventory title bar should move the window"
    page.keyboard.press("Escape")
    wait("escape_closes_inventory", lambda: not ui()["visible"])
    page.keyboard.press("i")
    wait("inventory_reopens_on_saved_page", lambda: ui()["visible"] and ui()["page"] == 1)
    assert ui()["window_rect"][:2] == moved[:2]
    page.screenshot(path=str(output / "inventory-moved-window.png"))
    page.keyboard.press("Escape")
    return {"sword": item(10), "potion": item(27001), "ui": ui()}
