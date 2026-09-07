"""Deterministic Godot texture settings for generated selected actor PNGs."""

from pathlib import Path

ACTOR_TEXTURE_IMPORT = (
    '[remap]\nimporter="texture"\ntype="CompressedTexture2D"\n\n'
    "[params]\ncompress/mode=0\nmipmaps/generate=true\n"
    "detect_3d/compress_to=0\nprocess/fix_alpha_border=true\n"
)


def write_actor_texture_import(path: Path) -> Path:
    """Write the selected-actor policy beside one source PNG."""
    if path.suffix.lower() != ".png":
        raise ValueError(f"Actor texture policy requires a PNG: {path}")
    sidecar = path.with_suffix(path.suffix + ".import")
    sidecar.write_text(ACTOR_TEXTURE_IMPORT)
    return sidecar


def configure_actor_texture_imports(actors_directory: Path) -> list[Path]:
    """Configure every generated actor PNG in one selected profile output."""
    if not actors_directory.is_dir():
        raise ValueError(f"Missing generated actor directory: {actors_directory}")
    return [write_actor_texture_import(path) for path in sorted(actors_directory.glob("*.png"))]
