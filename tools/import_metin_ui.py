#!/usr/bin/env python3
"""Convert a selected, pinned original UI fixture without executing archive code."""

import argparse
import hashlib
import json
import re
import shlex
from pathlib import Path, PurePosixPath

from fetch_test_assets import METIN_COMMIT, ROOT
from import_metin_intro import INTRO_REFERENCES, selected_intro_assets
from metin_archive import Archive, virtual_path, write_json
from PIL import Image
from PIL import __version__ as pillow_version

UI_ROOT = "ymir work/ui/"
OUTPUT = ROOT / "client/assets/imported/ui"
STATUS_WINDOW_ASSETS = (
    "public/parameter_slot_01.sub",
    "game/windows/box_face.sub",
    "game/windows/face_warrior.sub",
    "game/windows/btn_plus_up.sub",
    "game/windows/btn_plus_over.sub",
    "game/windows/btn_plus_down.sub",
    "game/windows/btn_minus_up.sub",
    "game/windows/btn_minus_over.sub",
    "game/windows/btn_minus_down.sub",
)
STATUS_ENGLISH_WINDOW_ROOT = "locale/en/ui/windows/"
STATUS_ENGLISH_WINDOW_ASSETS = (
    "title_status.sub",
    "label_level.sub",
    "label_cur_exp.sub",
    "label_last_exp.sub",
    "label_std.sub",
    "label_uppt.sub",
    "label_std_item1.sub",
    "label_std_item2.sub",
    "label_ext.sub",
    "label_ext_item1.sub",
    "label_ext_item2.sub",
    "tab_1.sub",
    "tab_2.sub",
    "tab_3.sub",
    "tab_4.sub",
)
TARGET_WINDOW_ASSETS = ("pattern/gauge_red.tga",)
REFERENCES = (
    "bin/pack/locale_en/locale/en/ui/taskbar.py",
    "bin/pack/locale_en/locale/en/ui/inventorywindow.py",
    "bin/pack/locale_en/locale/en/ui/systemdialog.py",
    "bin/pack/locale_en/locale/en/locale_game.txt",
    "bin/pack/locale_en/locale/en/locale_interface.txt",
    "bin/pack/uiscript/uiscript/minimap.py",
    "bin/pack/uiscript/uiscript/atlaswindow.py",
    "bin/pack/uiscript/uiscript/characterwindow.py",
    "bin/pack/uiscript/uiscript/mousebuttonwindow.py",
    "bin/pack/root/uitaskbar.py",
    "bin/pack/root/uicharacter.py",
    "bin/pack/root/uiinventory.py",
    "bin/pack/root/uiminimap.py",
    "bin/pack/root/uichat.py",
    "bin/pack/root/colorinfo.py",
    "bin/pack/root/uitooltip.py",
    "bin/pack/root/ui.py",
    "bin/pack/root/localeinfo.py",
    "bin/pack/root/interfacemodule.py",
    "bin/pack/root/game.py",
    "bin/pack/root/uiscriptlocale.py",
    "src/EterLib/GrpSubImage.cpp",
    "src/EterLib/GrpText.cpp",
    "src/EterLib/GrpFontTexture.cpp",
    "src/UserInterface/PythonMiniMap.cpp",
    "src/UserInterface/PythonChat.cpp",
    "src/UserInterface/PythonChat.h",
) + INTRO_REFERENCES


def selected_assets():
    """Explicit HUD/window fixture; no recursive archive or reference-code imports."""
    names = {
        "equipment_bg_without_ring.tga",
        "pattern/taskbar_base.tga",
        "pattern/horizontalbar_left.tga",
        "pattern/horizontalbar_center.tga",
        "pattern/horizontalbar_right.tga",
        "public/slot_base.sub",
        "public/parameter_slot_05.sub",
        "game/windows/money_icon.sub",
        "game/taskbar/gauge.sub",
        "game/taskbar/exp_gauge.sub",
        "game/taskbar/exp_gauge_point.sub",
        "game/taskbar/quickslot_button_board.sub",
        "game/taskbar/rampage_01/00.sub",
        "minimap/minimap.sub",
        "minimap/minimap_open_default.sub",
        "minimap/playermark.sub",
        "minimap/whitemark.sub",
        "minimap_image_filter.dds",
        "minimap_camera.dds",
        "atlas/metin2_map_a1/atlas.sub",
        "public/scrollbar_small_thin_middle_button_01.sub",
    }
    for stem in (
        "character_button",
        "inventory_button",
        "community_button",
        "system_button",
        "mouse_button_move",
        "mouse_button_attack",
        "mouse_button_camera",
        "chat_button",
        "send_chat_button",
        "send_whisper_button",
        "open_chat_log_button",
        "quickslot_upbutton",
        "quickslot_downbutton",
    ):
        names.update(f"game/taskbar/{stem}_{state:02}.sub" for state in range(1, 4))
    for stem in (
        "close_button",
        "small_button",
        "xsmall_button",
        "middle_button",
        "large_button",
        "xlarge_button",
        "slot_cover_button",
    ):
        names.update(f"public/{stem}_{state:02}.sub" for state in range(1, 4))
    for size in ("small", "large"):
        names.update(f"game/windows/tab_button_{size}_{state:02}.sub" for state in range(1, 4))
    for direction in ("up", "down"):
        names.update(
            f"public/scrollbar_small_thin_{direction}_button_{state:02}.sub"
            for state in range(1, 4)
        )
    for stem in ("minimap_scaleup", "minimap_scaledown", "minimap_close", "atlas_open"):
        names.update(f"minimap/{stem}_{state}.sub" for state in ("default", "over", "down"))
    for key in ("1", "2", "3", "4", "f1", "f2", "f3", "f4"):
        names.add(f"game/taskbar/{key}.sub")
    for gauge in ("hp", "sp", "st"):
        names.update(f"pattern/{gauge}gauge/{frame:02}.tga" for frame in range(1, 8))
    for board in ("board", "thinboard"):
        names.update(
            f"pattern/{board}_corner_{corner}.tga"
            for corner in ("lefttop", "leftbottom", "righttop", "rightbottom")
        )
        names.update(
            f"pattern/{board}_line_{side}.tga" for side in ("left", "right", "top", "bottom")
        )
    names.add("skill/warrior/palbang_01.sub")
    names.add("pattern/board_base.tga")
    for part in ("left", "center", "right"):
        names.add(f"pattern/titlebar_{part}.tga")
    for part in ("left", "middle", "right"):
        names.add(f"pattern/chat_bar_{part}.tga")
        names.add(f"pattern/chatlogwindow_titlebar_{part}.tga")
    return sorted(
        {UI_ROOT + name for name in names}
        | {UI_ROOT + name for name in STATUS_WINDOW_ASSETS}
        | {UI_ROOT + name for name in TARGET_WINDOW_ASSETS}
        | {STATUS_ENGLISH_WINDOW_ROOT + name for name in STATUS_ENGLISH_WINDOW_ASSETS}
        | {
            "icon/item/00010.tga",
            "icon/item/07000.tga",
            "icon/item/27001.tga",
            "icon/item/27002.tga",
        }
        | {
            f"icon/face/{source_class}_{sex}.tga"
            for source_class in ("warrior", "assassin", "sura", "shaman")
            for sex in ("m", "w")
        }
        | set(selected_intro_assets())
    )


def sub_image(text, descriptor):
    """Read atlas coordinates; v1 has a UI search root, v2 is descriptor-relative."""
    fields = {}
    for line in text.splitlines():
        tokens = shlex.split(line, comments=True)
        if not tokens:
            continue
        if len(tokens) != 2 or tokens[0].lower() in fields:
            raise ValueError(f"Malformed or duplicate sub-image field: {line!r}")
        fields[tokens[0].lower()] = tokens[1]
    required = {"title", "version", "image", "left", "top", "right", "bottom"}
    if set(fields) != required or fields["title"].lower() != "subimage":
        raise ValueError(f"Invalid sub-image descriptor: {descriptor}")
    version = fields["version"]
    if version not in ("1.0", "2.0"):
        raise ValueError(f"Unsupported sub-image version: {version}")
    image = fields["image"].replace("\\", "/")
    base = (
        UI_ROOT if version == "1.0" else str(PurePosixPath(virtual_path(descriptor)).parent) + "/"
    )
    atlas = virtual_path(base + image)
    crop = tuple(int(fields[key]) for key in ("left", "top", "right", "bottom"))
    left, top, right, bottom = crop
    if not (0 <= left < right and 0 <= top < bottom):
        raise ValueError(f"Invalid sub-image rectangle: {crop}")
    return atlas, crop


def output_path(name):
    normalized = virtual_path(name)
    if normalized.startswith(UI_ROOT):
        normalized = normalized[len(UI_ROOT) :]
    elif not normalized.startswith(("icon/item/", "icon/face/", "locale/en/ui/")):
        raise ValueError(f"Asset outside selected UI/icon namespace: {name}")
    return Path(normalized).with_suffix(".png")


def crop_image(image, crop):
    """Reject out-of-bounds crops instead of Pillow's silent transparent padding."""
    if crop is None:
        return image.convert("RGBA")
    left, top, right, bottom = crop
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ValueError(f"Sub-image rectangle {crop} exceeds image size {image.size}")
    return image.convert("RGBA").crop(crop)


def save_png(image, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".png.tmp")
    image.save(temporary, format="PNG", compress_level=9)
    temporary.replace(output)
    # Decoded pixels must round-trip exactly; no resize, tint, or lossy encoding.
    with Image.open(output) as saved:
        if saved.mode != "RGBA" or saved.tobytes() != image.tobytes():
            raise ValueError(f"UI PNG pixel mismatch: {output}")
    # UI pixels also appear on 3D pickup sprites. Never let 3D auto-detection turn
    # the shared icon into a lossy block-compressed or mipmapped HUD texture.
    output.with_suffix(".png.import").write_text(
        '[remap]\nimporter="texture"\ntype="CompressedTexture2D"\n\n'
        "[params]\ncompress/mode=0\nmipmaps/generate=false\n"
        "detect_3d/compress_to=0\nprocess/fix_alpha_border=false\n"
    )
    return hashlib.sha256(output.read_bytes()).hexdigest()


def stitch_yongan(archive, output_root=None):
    output_root = OUTPUT if output_root is None else output_root
    tiles = {
        (x, z): f"bin/pack/OutdoorA1/metin2_map_a1/{x:03}{z:03}/minimap.dds"
        for x in range(4)
        for z in range(5)
    }
    archive.fetch_many(tiles.values())
    canvas = None
    tile_size = None
    for (x, z), source in tiles.items():
        with Image.open(archive.get(source)) as original:
            tile = original.convert("RGBA")
        if tile_size is None:
            tile_size = tile.size
            canvas = Image.new("RGBA", (tile.width * 4, tile.height * 5))
        elif tile.size != tile_size:
            raise ValueError(f"Inconsistent minimap tile dimensions: {source}: {tile.size}")
        canvas.paste(tile, (x * tile.width, z * tile.height))
    output = output_root / "maps/metin2_map_a1.png"
    sha256 = save_png(canvas, output)
    return {
        "resource": "res://assets/imported/ui/maps/metin2_map_a1.png",
        "width": canvas.width,
        "height": canvas.height,
        "bounds_m": [1024, 1280],
        "origin_m": [0, 0],
        "axes": {"right": "+x", "down": "+z"},
        "tile_dimensions": list(tile_size),
        "tile_meters": 256,
        "sources": [{"grid": list(grid), "source": source} for grid, source in tiles.items()],
        "sha256": sha256,
        "rgba_sha256": hashlib.sha256(canvas.tobytes()).hexdigest(),
    }


def convert(archive, *, skill_icons=(), output_root=None):
    output_root = OUTPUT if output_root is None else output_root
    names = set(selected_assets())
    for icon in skill_icons:
        if not isinstance(icon, str) or not re.fullmatch(
            r"skill/(warrior|assassin|sura|shaman)/[a-z0-9_]+", icon
        ):
            raise ValueError("Invalid selected class skill icon")
        names.add(UI_ROOT + icon + ".sub")
    paths = {name: archive.resolve(name) for name in sorted(names)}
    archive.fetch_many([*paths.values(), *REFERENCES])
    prepared = {}
    for name, source in paths.items():
        atlas_name, crop = None, None
        if source.lower().endswith(".sub"):
            atlas_name, crop = sub_image(archive.get(source).read_text(), name)
        atlas = archive.resolve(atlas_name) if atlas_name else None
        prepared[name] = {"source": source, "atlas": atlas, "crop": crop}
    archive.fetch_many(entry["atlas"] for entry in prepared.values() if entry["atlas"])
    manifest = {
        "version": 1,
        "repository": "https://git.old-metin2.com/metin2/client",
        "commit": METIN_COMMIT,
        "converter": "tools/import_metin_ui.py",
        "pillow_version": pillow_version,
        "references": list(REFERENCES),
        "assets": {},
    }
    destinations = set()
    for name, entry in prepared.items():
        relative = output_path(name)
        if relative in destinations:
            raise ValueError(f"Duplicate generated UI destination: {relative}")
        destinations.add(relative)
        source = archive.get(entry["atlas"] or entry["source"])
        with Image.open(source) as original:
            converted = crop_image(original, entry["crop"])
            original_size = list(original.size)
        output = output_root / relative
        sha256 = save_png(converted, output)
        manifest["assets"][name] = {
            **entry,
            "resource": "res://assets/imported/ui/" + relative.as_posix(),
            "width": converted.width,
            "height": converted.height,
            "atlas_dimensions": original_size if entry["atlas"] else None,
            "sha256": sha256,
            "rgba_sha256": hashlib.sha256(converted.tobytes()).hexdigest(),
        }
    manifest["maps"] = {"metin2_map_a1": stitch_yongan(archive, output_root)}
    manifest["sources"] = dict(sorted(archive.used.items()))
    write_json(output_root / "manifest.json", manifest)
    print(f"Converted {len(prepared)} UI images from {len(archive.used)} pinned source files")
    print(f"Manifest: {output_root / 'manifest.json'}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline", action="store_true", help="Require all pinned sources in cache"
    )
    parser.add_argument(
        "--skill-inventory",
        type=Path,
        help="Include the explicitly discovered classic class skill icons",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    archive = Archive(offline=args.offline)
    archive.inventory()
    icons = []
    skill_catalog = ROOT / "client/assets/imported/skills/catalog.v1.json"
    if skill_catalog.is_file():
        catalog = json.loads(skill_catalog.read_text())
        if (
            catalog.get("schema") != "mt2spacetime.skills"
            or catalog.get("version") != 1
            or catalog.get("source_revision") != METIN_COMMIT
        ):
            raise ValueError("Expected pinned installed skill catalog")
        icons.extend(skill["icon"] for skill in catalog["skills"])
    if args.skill_inventory:
        inventory = json.loads(args.skill_inventory.read_text())
        if (
            inventory.get("schema") != "mt2spacetime.skill-source-inventory"
            or inventory.get("source_revision") != METIN_COMMIT
        ):
            raise ValueError("Expected pinned class skill inventory")
        icons.extend(skill["icon"] for skill in inventory["skills"])
    convert(archive, skill_icons=icons, output_root=args.output)


if __name__ == "__main__":
    main()
