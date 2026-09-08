"""Pure, fail-closed readers for the two selected Metin2 mesh effects.

The binary reader implements only the ``EffectData`` (MDE v001) layout used by
the pinned click-selection fixtures.  The text reader accepts only the mesh
script records needed by those fixtures.  Unknown groups, fields, movement
types, binary versions, and render modes are rejected rather than guessed.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass

from content_formats import LegacyNode, parse_legacy_script

MDE_V001_HEADER = b"EffectData\0"
MAX_MDE_BYTES = 8 * 1024 * 1024
MAX_GEOMETRIES = 8
MAX_FRAMES = 256
MAX_VERTICES = 65_536
MAX_INDICES = 196_608
MAX_TEXTURE_VERTICES = 65_536
MAX_SCRIPT_MESHES = 4
MAX_TIME_EVENTS = 256


class EffectMeshFormatError(ValueError):
    """A selected effect record is malformed or outside the supported subset."""


@dataclass(frozen=True, slots=True)
class MdeFrame:
    visibility: float
    positions: tuple[tuple[float, float, float], ...]
    position_indices: tuple[int, ...]
    texture_coordinates: tuple[tuple[float, float], ...]
    texture_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class MdeGeometry:
    name: str
    texture_path: str
    frames: tuple[MdeFrame, ...]


@dataclass(frozen=True, slots=True)
class MdeFile:
    version: int
    frame_count: int
    geometries: tuple[MdeGeometry, ...]


@dataclass(frozen=True, slots=True)
class PositionEvent:
    time: float
    movement_type: str
    position: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class AlphaEvent:
    time: float
    value: float


@dataclass(frozen=True, slots=True)
class MeshElement:
    billboard_type: int
    blending_enabled: bool
    blending_source: int
    blending_destination: int
    texture_animation_loop: bool
    texture_frame_delay: float
    texture_start_frame: int
    color_operation: int
    color_factor: tuple[float, float, float, float]
    alpha_events: tuple[AlphaEvent, ...]


@dataclass(frozen=True, slots=True)
class MeshScript:
    start_time: float
    position_events: tuple[PositionEvent, ...]
    mesh_file: str
    animation_loop: bool
    animation_loop_count: int
    frame_delay: float
    elements: tuple[MeshElement, ...]


@dataclass(frozen=True, slots=True)
class MseFile:
    bounding_sphere_radius: float
    bounding_sphere_position: tuple[float, float, float]
    meshes: tuple[MeshScript, ...]


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = memoryview(data)
        self.offset = 0

    def read(self, size: int, label: str) -> memoryview:
        if size < 0 or self.offset + size > len(self.data):
            raise EffectMeshFormatError(
                f"Truncated MDE while reading {label} at byte {self.offset}"
            )
        result = self.data[self.offset : self.offset + size]
        self.offset += size
        return result

    def unpack(self, layout: str, label: str) -> tuple:
        size = struct.calcsize(layout)
        return struct.unpack(layout, self.read(size, label))

    def u32(self, label: str) -> int:
        return self.unpack("<I", label)[0]

    def i32(self, label: str) -> int:
        return self.unpack("<i", label)[0]

    def f32(self, label: str) -> float:
        value = self.unpack("<f", label)[0]
        if not math.isfinite(value):
            raise EffectMeshFormatError(f"Non-finite {label}")
        return value

    def fixed_text(self, size: int, label: str) -> str:
        raw = bytes(self.read(size, label))
        terminator = raw.find(b"\0")
        if terminator < 0:
            raise EffectMeshFormatError(f"Unterminated {label}")
        if any(raw[terminator + 1 :]):
            raise EffectMeshFormatError(f"Nonzero padding in {label}")
        try:
            return raw[:terminator].decode("ascii")
        except UnicodeDecodeError as error:
            raise EffectMeshFormatError(f"Non-ASCII {label}") from error


def _bounded_count(value: int, maximum: int, label: str, *, minimum: int = 1) -> int:
    if not minimum <= value <= maximum:
        raise EffectMeshFormatError(f"Out-of-range {label}: {value}")
    return value


def d3dx_color_byte(value: float) -> int:
    """Match the D3DXCOLOR-to-DWORD channel conversion used by the renderer."""
    if not math.isfinite(value):
        raise EffectMeshFormatError("Cannot pack a non-finite D3DXCOLOR channel")
    if value <= 0.0:
        return 0
    if value >= 1.0:
        return 255
    return int(value * 255.0 + 0.5)


def parse_mde(data: bytes) -> MdeFile:
    """Parse one selected binary MDE v001 file without external libraries."""
    if not isinstance(data, bytes):
        raise TypeError("MDE input must be bytes")
    if len(data) > MAX_MDE_BYTES:
        raise EffectMeshFormatError(f"MDE exceeds {MAX_MDE_BYTES} bytes")
    reader = _Reader(data)
    header = bytes(reader.read(len(MDE_V001_HEADER), "header"))
    if header != MDE_V001_HEADER:
        if header.startswith(b"MDEData002"):
            raise EffectMeshFormatError("Unsupported MDEData002 record")
        raise EffectMeshFormatError(f"Unsupported MDE header {header!r}")

    geometry_count = _bounded_count(reader.i32("geometry count"), MAX_GEOMETRIES, "geometry count")
    frame_count = _bounded_count(reader.i32("frame count"), MAX_FRAMES, "frame count")
    geometries: list[MdeGeometry] = []
    for geometry_index in range(geometry_count):
        prefix = f"geometry {geometry_index}"
        name = reader.fixed_text(32, f"{prefix} name")
        if not name:
            raise EffectMeshFormatError(f"Empty {prefix} name")
        texture_path = reader.fixed_text(128, f"{prefix} texture path")
        if not texture_path:
            raise EffectMeshFormatError(f"Empty {prefix} texture path")
        vertex_count = _bounded_count(
            reader.u32(f"{prefix} vertex count"), MAX_VERTICES, f"{prefix} vertex count"
        )
        index_count = _bounded_count(
            reader.u32(f"{prefix} index count"), MAX_INDICES, f"{prefix} index count", minimum=3
        )
        texture_vertex_count = _bounded_count(
            reader.u32(f"{prefix} texture vertex count"),
            MAX_TEXTURE_VERTICES,
            f"{prefix} texture vertex count",
        )
        if index_count % 3:
            raise EffectMeshFormatError(f"{prefix} index count is not a triangle list")

        # Reject impossible declared payloads before allocating per-frame tuples.
        frame_bytes = (
            4 + vertex_count * 12 + index_count * 4 + texture_vertex_count * 8 + index_count * 4
        )
        if frame_bytes * frame_count > len(data) - reader.offset:
            raise EffectMeshFormatError(f"Truncated MDE payload for {prefix}")

        frames: list[MdeFrame] = []
        reference_position_indices: tuple[int, ...] | None = None
        reference_texture_indices: tuple[int, ...] | None = None
        reference_texture_coordinates: tuple[tuple[float, float], ...] | None = None
        for frame_index in range(frame_count):
            frame_prefix = f"{prefix} frame {frame_index}"
            visibility = reader.f32(f"{frame_prefix} visibility")
            positions = tuple(
                tuple(
                    reader.f32(f"{frame_prefix} position {point} axis {axis}") for axis in range(3)
                )
                for point in range(vertex_count)
            )
            position_indices = tuple(
                reader.i32(f"{frame_prefix} position index {index}") for index in range(index_count)
            )
            texture_coordinates = tuple(
                tuple(reader.f32(f"{frame_prefix} UV {point} axis {axis}") for axis in range(2))
                for point in range(texture_vertex_count)
            )
            texture_indices = tuple(
                reader.i32(f"{frame_prefix} texture index {index}") for index in range(index_count)
            )
            if any(index < 0 or index >= vertex_count for index in position_indices):
                raise EffectMeshFormatError(f"Out-of-range position index in {frame_prefix}")
            if any(index < 0 or index >= texture_vertex_count for index in texture_indices):
                raise EffectMeshFormatError(f"Out-of-range texture index in {frame_prefix}")
            if reference_position_indices is None:
                reference_position_indices = position_indices
                reference_texture_indices = texture_indices
                reference_texture_coordinates = texture_coordinates
            elif (
                position_indices != reference_position_indices
                or texture_indices != reference_texture_indices
            ):
                raise EffectMeshFormatError(f"Animated topology changes in {frame_prefix}")
            elif texture_coordinates != reference_texture_coordinates:
                raise EffectMeshFormatError(f"Animated texture coordinates in {frame_prefix}")
            frames.append(
                MdeFrame(
                    visibility=visibility,
                    positions=positions,
                    position_indices=position_indices,
                    texture_coordinates=texture_coordinates,
                    texture_indices=texture_indices,
                )
            )
        geometries.append(MdeGeometry(name=name, texture_path=texture_path, frames=tuple(frames)))

    if reader.offset != len(data):
        raise EffectMeshFormatError(f"Unexpected trailing MDE data at byte {reader.offset}")
    return MdeFile(version=1, frame_count=frame_count, geometries=tuple(geometries))


def _finite(token: str, label: str, *, minimum: float | None = None) -> float:
    try:
        value = float(token)
    except ValueError as error:
        raise EffectMeshFormatError(f"Invalid {label}: {token!r}") from error
    if not math.isfinite(value) or (minimum is not None and value < minimum):
        raise EffectMeshFormatError(f"Out-of-range {label}: {token!r}")
    return value


def _integer(token: str, label: str, minimum: int, maximum: int) -> int:
    if not re.fullmatch(r"-?[0-9]+", token):
        raise EffectMeshFormatError(f"Invalid {label}: {token!r}")
    value = int(token)
    if not minimum <= value <= maximum:
        raise EffectMeshFormatError(f"Out-of-range {label}: {value}")
    return value


def _field(node: LegacyNode, name: str, count: int = 1) -> list[str]:
    values = node.fields.get(name)
    if values is None:
        raise EffectMeshFormatError(f"Missing {name!r} in {node.name or '<root>'}")
    if len(values) != count:
        raise EffectMeshFormatError(f"{name!r} in {node.name or '<root>'} needs {count} values")
    return values


def _only_fields(node: LegacyNode, allowed: set[str]) -> None:
    unknown = set(node.fields) - allowed
    if unknown:
        raise EffectMeshFormatError(
            f"Unsupported fields in {node.name or '<root>'}: {sorted(unknown)}"
        )


def _only_groups(node: LegacyNode, allowed: set[tuple[str, str]]) -> None:
    unknown = {(group.kind, group.name) for group in node.groups} - allowed
    if unknown:
        raise EffectMeshFormatError(
            f"Unsupported groups in {node.name or '<root>'}: {sorted(unknown)}"
        )


def _flag(token: str, label: str) -> bool:
    return bool(_integer(token, label, 0, 1))


def _parse_position_events(node: LegacyNode) -> tuple[PositionEvent, ...]:
    _only_fields(node, set())
    _only_groups(node, set())
    if len(node.rows) > MAX_TIME_EVENTS:
        raise EffectMeshFormatError("Too many TimeEventPosition records")
    events: list[PositionEvent] = []
    for index, row in enumerate(node.rows):
        if len(row) != 5:
            raise EffectMeshFormatError(f"Malformed TimeEventPosition row {index}")
        time = _finite(row[0], f"position event {index} time", minimum=0.0)
        if row[1] != "MOVING_TYPE_DIRECT":
            raise EffectMeshFormatError(f"Unsupported position movement type {row[1]!r}")
        position = tuple(_finite(value, f"position event {index} coordinate") for value in row[2:])
        if events and time <= events[-1].time:
            raise EffectMeshFormatError("TimeEventPosition times must increase")
        events.append(PositionEvent(time, row[1], position))
    if not events:
        raise EffectMeshFormatError("TimeEventPosition must not be empty")
    return tuple(events)


def _parse_alpha_events(node: LegacyNode) -> tuple[AlphaEvent, ...]:
    _only_fields(node, set())
    _only_groups(node, set())
    if len(node.rows) > MAX_TIME_EVENTS:
        raise EffectMeshFormatError("Too many TimeEventAlpha records")
    events: list[AlphaEvent] = []
    for index, row in enumerate(node.rows):
        if len(row) != 2:
            raise EffectMeshFormatError(f"Malformed TimeEventAlpha row {index}")
        time = _finite(row[0], f"alpha event {index} time", minimum=0.0)
        value = _finite(row[1], f"alpha event {index} value")
        if events and time <= events[-1].time:
            raise EffectMeshFormatError("TimeEventAlpha times must increase")
        events.append(AlphaEvent(time, value))
    return tuple(events)


def _parse_element(node: LegacyNode, blend_pairs) -> MeshElement:
    allowed = {
        "BillboardType",
        "BlendingEnable",
        "BlendingSrcType",
        "BlendingDestType",
        "TextureAnimationLoopEnable",
        "TextureAnimationFrameDelay",
        "TextureAnimationStartFrame",
        "ColorOperationType",
        "ColorFactor",
    }
    _only_fields(node, allowed)
    _only_groups(node, {("list", "TimeEventAlpha")})
    alpha_groups = [group for group in node.groups if group.name == "TimeEventAlpha"]
    if len(alpha_groups) != 1:
        raise EffectMeshFormatError(f"{node.name} needs one TimeEventAlpha list")
    billboard = _integer(_field(node, "BillboardType")[0], "BillboardType", 0, 255)
    if billboard != 0:
        raise EffectMeshFormatError(f"Unsupported BillboardType {billboard}")
    source = _integer(_field(node, "BlendingSrcType")[0], "BlendingSrcType", 0, 255)
    destination = _integer(_field(node, "BlendingDestType")[0], "BlendingDestType", 0, 255)
    if (source, destination) not in blend_pairs:
        raise EffectMeshFormatError(f"Unsupported blend pair {source}/{destination}")
    color_operation = _integer(_field(node, "ColorOperationType")[0], "ColorOperationType", 0, 255)
    if color_operation != 4:
        raise EffectMeshFormatError(f"Unsupported ColorOperationType {color_operation}")
    color = tuple(
        _finite(value, "ColorFactor component") for value in _field(node, "ColorFactor", 4)
    )
    if any(component < 0.0 or component > 1.0 for component in color):
        raise EffectMeshFormatError("ColorFactor components must be in [0, 1]")
    frame_delay = _finite(
        _field(node, "TextureAnimationFrameDelay")[0],
        "TextureAnimationFrameDelay",
        minimum=0.000_001,
    )
    return MeshElement(
        billboard_type=billboard,
        blending_enabled=_flag(_field(node, "BlendingEnable")[0], "BlendingEnable"),
        blending_source=source,
        blending_destination=destination,
        texture_animation_loop=_flag(
            _field(node, "TextureAnimationLoopEnable")[0], "TextureAnimationLoopEnable"
        ),
        texture_frame_delay=frame_delay,
        texture_start_frame=_integer(
            _field(node, "TextureAnimationStartFrame")[0],
            "TextureAnimationStartFrame",
            0,
            MAX_FRAMES,
        ),
        color_operation=color_operation,
        color_factor=color,
        alpha_events=_parse_alpha_events(alpha_groups[0]),
    )


def _parse_mesh(node: LegacyNode, blend_pairs) -> MeshScript:
    allowed = {
        "StartTime",
        "MeshFileName",
        "MeshAnimationLoopEnable",
        "MeshAnimationLoopCount",
        "MeshAnimationFrameDelay",
        "MeshElementCount",
    }
    _only_fields(node, allowed)
    position_groups = [group for group in node.groups if group.name == "TimeEventPosition"]
    element_count = _integer(
        _field(node, "MeshElementCount")[0], "MeshElementCount", 1, MAX_GEOMETRIES
    )
    expected_elements = {f"MeshElement{index:02}" for index in range(element_count)}
    _only_groups(
        node,
        {("list", "TimeEventPosition"), *(("group", name) for name in expected_elements)},
    )
    if len(position_groups) != 1:
        raise EffectMeshFormatError("Mesh needs one TimeEventPosition list")
    actual_elements = [group for group in node.groups if group.kind == "group"]
    if (
        len(actual_elements) != element_count
        or {group.name for group in actual_elements} != expected_elements
    ):
        raise EffectMeshFormatError("MeshElementCount does not match numbered element groups")
    actual_elements.sort(key=lambda group: group.name)
    mesh_file = _field(node, "MeshFileName")[0]
    if not re.fullmatch(r"[A-Za-z0-9_. -]+\.mde", mesh_file, flags=re.IGNORECASE):
        raise EffectMeshFormatError(f"Unsupported MeshFileName {mesh_file!r}")
    return MeshScript(
        start_time=_finite(_field(node, "StartTime")[0], "StartTime", minimum=0.0),
        position_events=_parse_position_events(position_groups[0]),
        mesh_file=mesh_file,
        animation_loop=_flag(_field(node, "MeshAnimationLoopEnable")[0], "MeshAnimationLoopEnable"),
        animation_loop_count=_integer(
            _field(node, "MeshAnimationLoopCount")[0],
            "MeshAnimationLoopCount",
            0,
            1_000_000,
        ),
        frame_delay=_finite(
            _field(node, "MeshAnimationFrameDelay")[0],
            "MeshAnimationFrameDelay",
            minimum=0.000_001,
        ),
        elements=tuple(_parse_element(group, blend_pairs) for group in actual_elements),
    )


def parse_mse(text: str, *, blend_pairs=frozenset({(5, 2), (5, 6)})) -> MseFile:
    """Parse the strict mesh-only subset used by click_select target effects."""
    if not isinstance(text, str):
        raise TypeError("MSE input must be text")
    try:
        root = parse_legacy_script(text)
    except ValueError as error:
        raise EffectMeshFormatError(str(error)) from error
    return parse_mesh_root(root, blend_pairs=blend_pairs)


def parse_mesh_root(root: LegacyNode, *, blend_pairs=frozenset({(5, 2), (5, 6)})) -> MseFile:
    """Validate a mesh-only syntax tree selected by a complete effect adapter."""
    _only_fields(root, {"BoundingSphereRadius", "BoundingSpherePosition"})
    _only_groups(root, {("group", "Mesh")})
    if not 1 <= len(root.groups) <= MAX_SCRIPT_MESHES:
        raise EffectMeshFormatError("MSE must contain a bounded nonempty set of Mesh groups")
    radius_values = root.fields.get("BoundingSphereRadius", ["0"])
    position_values = root.fields.get("BoundingSpherePosition", ["0", "0", "0"])
    if len(radius_values) != 1 or len(position_values) != 3:
        raise EffectMeshFormatError("Malformed bounding sphere")
    radius = _finite(radius_values[0], "BoundingSphereRadius", minimum=0.0)
    position = tuple(_finite(value, "BoundingSpherePosition") for value in position_values)
    return MseFile(
        bounding_sphere_radius=radius,
        bounding_sphere_position=position,
        meshes=tuple(_parse_mesh(group, blend_pairs) for group in root.groups),
    )
