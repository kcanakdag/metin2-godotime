"""Actual canvas mouse/keyboard checks for the classic inventory in Web exports."""

import time


def _hover_point(page, ui, point):
    """Enter a slot from outside the window so ClassicSlot sees a real edge."""

    window = ui()["window_rect"]
    page.mouse.move(window[0] - 8, point[1])
    page.mouse.move(point[0], point[1], steps=6)


def exercise_inventory(page, snapshot, wait, output):
    """Read coordinates/state from the probe; perform every item action through visible UI."""

    # The four-minute session refresh deliberately drops and restores the world
    # connection. The client mirrors subscription rows and filters them by the
    # signed-in identity, so a read can land in the refresh window even though
    # the previous check just observed confirmed rows. Wait the gap out instead
    # of failing a state the player never lost.
    refresh_waits = []

    def settled(read, timeout=30.0):
        """Re-read a probe list until it has content or the refresh window passes."""

        start = time.monotonic()
        deadline = start + timeout
        while True:
            value = read()
            if value or time.monotonic() >= deadline:
                waited_ms = int((time.monotonic() - start) * 1000)
                if waited_ms > 500:
                    refresh_waits.append(
                        {
                            "waited_ms": waited_ms,
                            "connection_state": snapshot().get("connection_state"),
                        }
                    )
                    print(
                        "RECOVER empty probe list for %d ms (state=%s)"
                        % (waited_ms, snapshot().get("connection_state")),
                        flush=True,
                    )
                return value
            time.sleep(0.1)

    def inventory_rows():
        return settled(lambda: snapshot().get("inventory", []))

    def item(vnum):
        rows = inventory_rows()
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

    def item_point(row):
        """Resolve the real on-screen point of a confirmed row.

        Classic slot 255 is the equipment weapon slot, not a bag cell, and a
        bag cell on page II maps to the same grid position as page I.
        """

        cell = int(row["cell"])
        if cell == 255:
            origin = ui()["equipment_origin"]
            return [origin[0] + 16, origin[1] + 16]
        return cell_point(cell)

    def show_page_of(cell):
        """Make the bag page that owns a cell visible before clicking it."""

        wanted = int(cell) // 45
        if ui()["page"] == wanted:
            return
        click(ui()["tab_centers"][wanted])
        wait("inventory_switches_to_page_" + str(wanted), lambda: ui()["page"] == wanted)

    def own_row():
        def matching():
            state = snapshot()
            identity = state.get("identity")
            return [row for row in state.get("player_rows", []) if row.get("identity") == identity]

        return next(iter(settled(matching)), {})

    def at_full_health() -> bool:
        row = own_row()
        return bool(row) and int(row["health"]) >= int(row["max_health"])

    def right_click_row(row):
        """Re-enter the slot before clicking; a parked pointer misses rebuilt rows."""

        point = item_point(row)
        window = ui()["window_rect"]
        page.mouse.move(window[0] - 8, point[1])
        page.mouse.move(point[0], point[1], steps=6)
        page.mouse.click(point[0], point[1], button="right")

    wait("browser_receives_own_starter_items", lambda: len(inventory_rows()) == 2)
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
            _hover_point(page, ui, item_point(item(10)))
        return False

    _hover_point(page, ui, item_point(sword))
    wait("original_item_tooltip_appears", tooltip_shown, timeout=45)
    page.screenshot(path=str(output / "inventory-tooltip.png"))
    wait(
        "inventory_holds_confirmed_rows_for_actions",
        lambda: ensure_visible() and len(inventory_rows()) == 2,
        timeout=45,
    )
    # The field-combat phase already equipped the starter weapon, so the classic
    # right-click toggle is exercised as a real round trip: unequip from the
    # equipment slot, then equip again from the bag cell the server chose.
    entry_equipped = bool(item(10)["equipped"])
    if entry_equipped:
        right_click_row(item(10))
        wait("inventory_right_click_unequips_server_item", lambda: not item(10)["equipped"])
        show_page_of(item(10)["cell"])
    right_click_row(item(10))
    wait("inventory_right_click_equips_server_item", lambda: item(10)["equipped"])
    weapon = ui()["equipment_origin"]
    show_page_of(2)
    drag([weapon[0] + 16, weapon[1] + 16], cell_point(2))
    wait(
        "equipment_drag_unequips_into_bag",
        lambda: not item(10)["equipped"] and item(10)["cell"] == 2,
    )
    show_page_of(potion["cell"])
    drag(cell_point(potion["cell"]), ui()["quickslot_centers"][0])
    wait("potion_drag_binds_quickslot", lambda: ui()["quickslot_bindings"][0] == potion["id"])
    errors_before = len(snapshot().get("errors", []))
    charges_before = item(27001)["count"]
    health_before = int(own_row().get("health", 0))
    entry_full_health = at_full_health()
    page.keyboard.press("1")
    if entry_full_health:
        wait(
            "quickslot_sends_validated_potion_intent",
            lambda: len(snapshot()["errors"]) > errors_before,
        )
        wait("potion_rejection_keeps_charges", lambda: item(27001)["count"] == charges_before)
    else:
        wait(
            "quickslot_sends_validated_potion_intent",
            lambda: item(27001)["count"] == charges_before - 1,
        )
        assert len(snapshot()["errors"]) == errors_before, (
            "A damaged character's potion must be accepted rather than rejected"
        )
        wait("potion_acceptance_heals_owner", lambda: int(own_row()["health"]) > health_before)
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
    return {
        "sword": item(10),
        "potion": item(27001),
        "ui": ui(),
        "recoveries": recoveries,
        "refresh_waits": refresh_waits,
        "entry_equipped": entry_equipped,
        "entry_full_health": entry_full_health,
    }
