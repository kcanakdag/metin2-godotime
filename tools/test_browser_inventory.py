"""Actual canvas mouse/keyboard checks for the classic inventory in Web exports."""

import time


def _hover_sword(page, ui, cell_point, cell):
    window = ui()["window_rect"]
    target = cell_point(cell)
    page.mouse.move(window[0] - 8, target[1])
    page.mouse.move(*target, steps=6)


def exercise_inventory(page, snapshot, wait, output):
    """Read coordinates/state from the probe; perform every item action through visible UI."""

    def item(vnum):
        rows = snapshot()["inventory"]
        for row in rows:
            if row["vnum"] == vnum:
                return row
        raise AssertionError(
            "Starter item vnum {} is missing from the browser inventory; rows={}".format(
                vnum, [(row["vnum"], row["cell"], row["equipped"]) for row in rows]
            )
        )

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
    # ClassicSlot exposes its tooltip on the real mouse-enter edge. Enter from
    # outside the newly shown inventory and retain intermediate motion events so
    # opening the window under a previously stationary pointer cannot lose it.
    #
    # The four-minute session refresh deliberately drops and restores the world
    # connection. A build that closes the bag on that disconnect leaves the
    # pointer over a hidden window, so re-open and re-enter instead of failing a
    # hover the player never abandoned. The tooltip itself stays mandatory.
    recoveries = []

    def ensure_visible() -> bool:
        """Re-open the bag only when it closed without the harness closing it."""
        if ui()["visible"]:
            return True
        if len(recoveries) >= 3:
            return False
        state = snapshot().get("connection_state")
        print("RECOVER inventory closed without input (state=%s)" % state, flush=True)
        recoveries.append({"connection_state": state})
        page.keyboard.press("i")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not ui()["visible"]:
            time.sleep(0.1)
        return ui()["visible"]

    def tooltip_shown() -> bool:
        if ui()["tooltip_visible"]:
            return True
        if ensure_visible():
            _hover_sword(page, ui, cell_point, sword["cell"])
        return False

    _hover_sword(page, ui, cell_point, sword["cell"])
    wait("original_item_tooltip_appears", tooltip_shown, timeout=45)
    page.screenshot(path=str(output / "inventory-tooltip.png"))
    wait(
        "inventory_holds_confirmed_rows_for_actions",
        lambda: ensure_visible() and len(snapshot().get("inventory", [])) == 2,
        timeout=45,
    )
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
    return {"sword": item(10), "potion": item(27001), "ui": ui(), "recoveries": recoveries}
