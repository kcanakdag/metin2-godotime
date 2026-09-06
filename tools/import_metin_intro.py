"""Explicit original entry-screen fixture at the shared Metin2 archive pin."""

INTRO_REFERENCES = tuple(
    "bin/pack/locale_en/locale/en/ui/" + name + ".py"
    for name in (
        "loginwindow",
        "selectempirewindow",
        "selectcharacterwindow",
        "createcharacterwindow",
    )
) + tuple(
    "bin/pack/root/" + name + ".py"
    for name in ("intrologin", "introempire", "introselect", "introcreate")
)


def selected_intro_assets():
    """Keep only displayed intro artwork and its button states, not the archive UI tree."""
    locale = {
        "serverlist.sub",
        "login.sub",
        "select.sub",
        "login/loginwindow.sub",
        "select/name_warrior.sub",
        "empire/title.sub",
    }
    names = {
        "intro/pattern/background_pattern.tga",
        "intro/pattern/line_pattern.tga",
        "intro/select/background_alpha.sub",
        "intro/empire/atlas.sub",
        "public/parameter_slot_00.sub",
        "public/parameter_slot_03.sub",
        "public/parameter_slot_04.sub",
    }
    for suffix in ("a", "b", "c"):
        for prefix in ("empirearea", "empireareaflag", "empireflag"):
            names.add(f"intro/empire/{prefix}_{suffix}.sub")
    for side in ("left", "right"):
        for prefix in ("", "dragon_"):
            names.update(
                f"intro/select/{prefix}{side}_button_{state:02}.sub" for state in range(1, 4)
            )
    for part in ("left", "center", "right"):
        names.add(f"pattern/gauge_slot_{part}.tga")
    return sorted(
        {"ymir work/ui/" + name for name in names} | {"locale/en/ui/" + name for name in locale}
    )
