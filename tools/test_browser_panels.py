"""Real canvas interaction checks for the original minimap, atlas and chat windows."""

import math
import time


def exercise_panels(page, snapshot, wait, output):
    def state(kind):
        return snapshot()["ui"][kind]

    def click(point):
        page.mouse.click(*point)

    def drag(start, end):
        page.mouse.move(*start)
        page.mouse.down()
        page.mouse.move(*end, steps=20)
        page.mouse.up()

    wait("original_minimap_is_visible", lambda: state("map")["minimap_visible"])
    click(state("map")["minimap_close_center"])
    wait("minimap_close_button_works", lambda: not state("map")["minimap_visible"])
    click(state("map")["minimap_open_center"])
    wait("minimap_reopen_button_works", lambda: state("map")["minimap_visible"])
    scale = state("map")["minimap_meters_per_pixel"]
    click(state("map")["zoom_out_center"])
    wait("minimap_zoom_changes_scale", lambda: state("map")["minimap_meters_per_pixel"] > scale)
    click(state("map")["zoom_in_center"])
    page.keyboard.press("m")
    wait("M_opens_original_atlas", lambda: state("map")["atlas_visible"])
    assert state("map")["atlas_image_size"] == [171, 214]
    original = state("map")["atlas_rect"]
    title = state("map")["atlas_title_center"]
    drag(title, [title[0] - 90, title[1] + 90])
    wait(
        "atlas_title_drag_moves_window",
        lambda: math.dist(state("map")["atlas_rect"][:2], [original[0] - 90, original[1] + 90]) < 1,
    )
    page.screenshot(path=str(output / "original-atlas.png"))
    click(state("map")["atlas_close_center"])
    wait("atlas_close_button_works", lambda: not state("map")["atlas_visible"])
    click(state("map")["atlas_button_center"])
    wait("minimap_atlas_button_works", lambda: state("map")["atlas_visible"])
    page.keyboard.press("Escape")
    wait("Escape_closes_atlas", lambda: not state("map")["atlas_visible"])

    page.keyboard.press("Enter")
    wait("Enter_opens_original_chat_entry", lambda: state("chat")["editing"])
    page.keyboard.type("iml")
    assert not state("map")["atlas_visible"] and not snapshot()["ui"]["visible"]
    assert not state("chat")["history_visible"]
    page.keyboard.press("Escape")
    wait("Escape_cancels_chat_without_sending", lambda: not state("chat")["editing"])
    page.keyboard.press("l")
    wait("L_opens_original_chat_history", lambda: state("chat")["history_visible"])
    rectangle = state("chat")["history_rect"]
    title = [rectangle[0] + 180, rectangle[1] + 12]
    drag(title, [title[0] + 90, title[1] + 100])
    wait(
        "chat_history_title_drag_works",
        # The probe updates periodically. Wait for the final drag position before
        # using its resize-handle coordinates, not an in-flight intermediate frame.
        lambda: (
            math.dist(state("chat")["history_rect"][:2], [rectangle[0] + 90, rectangle[1] + 100])
            < 1
        ),
    )
    before = state("chat")["history_rect"]
    handle = state("chat")["history_resize_handle"]
    drag(handle, [handle[0] + 80, handle[1] + 90])
    wait(
        "chat_history_resizes",
        lambda: math.dist(state("chat")["history_rect"][2:], [before[2] + 80, before[3] + 90]) < 1,
    )
    time.sleep(0.3)
    page.screenshot(path=str(output / "original-chat-history.png"))
    click(state("chat")["history_close_center"])
    wait("chat_history_close_button_works", lambda: not state("chat")["history_visible"])
    return {"map": state("map"), "chat": state("chat")}


def exercise_chat_focus(page, snapshot, desktop, identity, wait, stop):
    """Send messages only in an isolated local world; verify movement at the other client."""

    def chat():
        return snapshot()["ui"]["chat"]

    def remote_position():
        return next(
            row["position"] for row in desktop()["rendered_actors"] if row["identity"] == identity
        )

    def walk(check):
        start = remote_position()
        page.keyboard.down("w")
        try:
            wait(check, lambda: math.dist(remote_position(), start) > 0.5, 6)
        finally:
            page.keyboard.up("w")
            stop()

    page.keyboard.press("Enter")
    wait(
        "chat_focus_opens_at_bottom_center",
        lambda: chat()["focused"] and chat()["entry_position"] == [340, 738],
    )
    start = remote_position()
    message = "ChatFocus" + str(time.time_ns())[-10:]
    page.keyboard.type(message)
    time.sleep(0.3)
    assert math.dist(remote_position(), start) < 0.1, "Typing must not move the character"
    page.keyboard.press("Enter")
    wait(
        "sending_chat_releases_keyboard_focus",
        lambda: not chat()["focused"] and not chat()["editing"],
    )
    wait(
        "chat_message_reaches_other_client",
        lambda: any(message in line for line in desktop()["ui"]["chat"]["history_lines"]),
    )
    walk("WASD_moves_after_sending_chat")

    page.keyboard.press("Enter")
    page.keyboard.type("cancel")
    page.keyboard.press("Escape")
    wait(
        "Escape_releases_chat_keyboard_focus",
        lambda: not chat()["focused"] and not chat()["editing"],
    )
    walk("WASD_moves_after_closing_chat")

    page.keyboard.press("Enter")
    page.keyboard.type("click cancel")
    page.mouse.click(640, 500)
    wait(
        "world_click_releases_chat_keyboard_focus",
        lambda: not chat()["focused"] and not chat()["editing"],
    )
    stop()
    wait("click_movement_stops_before_keyboard_check", lambda: snapshot()["activity"] == 0)
    walk("WASD_moves_after_clicking_out_of_chat")

    page.keyboard.press("l")
    wait("history_input_receives_focus", lambda: chat()["history_visible"] and chat()["focused"])
    page.keyboard.type(message + "History")
    page.keyboard.press("Enter")
    wait(
        "history_send_releases_focus_and_keeps_window",
        lambda: chat()["history_visible"] and not chat()["focused"],
    )
    walk("WASD_moves_with_unfocused_chat_history")
    page.keyboard.press("Escape")
