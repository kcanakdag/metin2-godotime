#!/usr/bin/env python3
"""Offline walk planner for the baked Yongan world.

The server trusts only its compiled world (`server/content/yongan.bin`): height,
terrain/collision attributes, authored building shapes and raised floors. Live
clients may not decide whether a path is clear, so every automated walk in the
quest harness has to follow the same rules. This module mirrors
`server/src/content.rs` (height, blocked, in_bounds, valid_target, clear_path)
and plans waypoints with the same 0.25 m segment sampling the reducer uses.

Evidence produced here is offline navigation data for a disposable test
database; it is not live gameplay acceptance by itself.
"""

from __future__ import annotations

import argparse
import heapq
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORLD = ROOT / "server/content/yongan.bin"
PLAYER_RADIUS = 0.45
STEP_M = 1.0
TILE_M = 16.0


class World:
    """Parsed `MT2YON02` world data with server-identical queries."""

    def __init__(self, data: bytes, *, require_magic: bool = True) -> None:
        if require_magic and data[:8] != b"MT2YON02":
            raise ValueError("Yongan world data is missing its container header.")
        self.data = data
        self.terrain_width = self._u32(8)
        self.terrain_depth = self._u32(12)
        self.width = self._u32(16)
        self.depth = self._u32(20)
        self.shape_count = self._u32(24)
        self.floor_count = self._u32(28)
        # Pre-decode the blob once: the queries below run tens of thousands of
        # times per plan and the raw struct reads dominate otherwise.
        self._terrain_cells = struct.unpack_from(
            "<%dH" % (self.terrain_width * self.terrain_depth), data, 32
        )
        attr = self._attr_offset()
        self._attrs = memoryview(data)[attr : attr + self.width * self.depth]
        shapes = self._shapes_offset()
        self._shapes = [
            struct.unpack_from("<13f", data, shapes + index * 52)
            for index in range(self.shape_count)
        ]
        floors = self._floors_offset()
        self._floors = [
            struct.unpack_from("<13f", data, floors + index * 52)
            for index in range(self.floor_count)
        ]
        # The server walks every shape/floor per query; a single plan issues
        # hundreds of thousands of queries, so bucket them into 16 m tiles.
        self._shape_tiles: dict[tuple[int, int], list[tuple[float, float, float, float]]] = {}
        for shape in self._shapes:
            if shape[0] > 0.5:
                cx, cz, radius = shape[3], shape[4], shape[11] + PLAYER_RADIUS
                box = (cx - radius, cx + radius, cz - radius, cz + radius)
            else:
                xs = [shape[3 + i * 2] for i in range(4)]
                zs = [shape[4 + i * 2] for i in range(4)]
                box = (
                    min(xs) - PLAYER_RADIUS,
                    max(xs) + PLAYER_RADIUS,
                    min(zs) - PLAYER_RADIUS,
                    max(zs) + PLAYER_RADIUS,
                )
            for tile in _tiles_for_box(box):
                self._shape_tiles.setdefault(tile, []).append(shape)
        self._floor_tiles: dict[tuple[int, int], list[tuple[float, ...]]] = {}
        for floor in self._floors:
            box = (floor[0], floor[1], floor[2], floor[3])
            for tile in _tiles_for_box(box, pad=0.0):
                self._floor_tiles.setdefault(tile, []).append(floor)
        self._height_cache: dict[tuple[float, float], float] = {}
        self._standable_cache: dict[tuple[float, float], bool] = {}

    @classmethod
    def load(cls, path: Path = DEFAULT_WORLD) -> "World":
        return cls(path.read_bytes())

    def _u32(self, offset: int) -> int:
        return struct.unpack_from("<I", self.data, offset)[0]

    def _f32(self, offset: int) -> float:
        return struct.unpack_from("<f", self.data, offset)[0]

    def _terrain(self, x: int, z: int) -> float:
        return self._terrain_cells[z * self.terrain_width + x] * 0.005

    def _attr_offset(self) -> int:
        return 32 + self.terrain_width * self.terrain_depth * 2

    def _shapes_offset(self) -> int:
        return self._attr_offset() + self.width * self.depth

    def _floors_offset(self) -> int:
        return self._shapes_offset() + self.shape_count * 52

    def in_bounds(self, x: float, z: float) -> bool:
        if not math.isfinite(x) or not math.isfinite(z):
            return False
        return (
            x >= PLAYER_RADIUS
            and z >= PLAYER_RADIUS
            and x < self.width - PLAYER_RADIUS
            and z < self.depth - PLAYER_RADIUS
        )

    def height(self, x: float, z: float) -> float:
        key = (round(x, 3), round(z, 3))
        cached = self._height_cache.get(key)
        if cached is not None:
            return cached
        value = self._height_uncached(key[0], key[1])
        if len(self._height_cache) < 2_000_000:
            self._height_cache[key] = value
        return value

    def _height_uncached(self, x: float, z: float) -> float:
        if not self.in_bounds(x, z):
            return 0.0
        gx = x * 0.5
        gz = z * 0.5
        ix = math.floor(gx)
        iz = math.floor(gz)
        u = gx - ix
        v = gz - iz
        if u + v <= 1.0:
            height = (
                self._terrain(ix, iz) * (1.0 - u - v)
                + self._terrain(ix + 1, iz) * u
                + self._terrain(ix, iz + 1) * v
            )
        else:
            height = (
                self._terrain(ix + 1, iz + 1) * (u + v - 1.0)
                + self._terrain(ix, iz + 1) * (1.0 - u)
                + self._terrain(ix + 1, iz) * (1.0 - v)
            )
        for floor in self._floor_tiles.get((math.floor(x / TILE_M), math.floor(z / TILE_M)), ()):
            if x < floor[0] or x > floor[1]:
                continue
            if z < floor[2] or z > floor[3]:
                continue
            a = (floor[4], floor[5], floor[6])
            b = (floor[7], floor[8], floor[9])
            c = (floor[10], floor[11], floor[12])
            det = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(det) < 0.0001:
                continue
            pu = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / det
            pv = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / det
            if pu >= -0.0001 and pv >= -0.0001 and pu + pv <= 1.0001:
                height = max(height, pu * a[1] + pv * b[1] + (1.0 - pu - pv) * c[1])
        return height

    @staticmethod
    def _segment_distance(
        x: float, z: float, a: tuple[float, float], b: tuple[float, float]
    ) -> float:
        dx = b[0] - a[0]
        dz = b[1] - a[1]
        length = max(dx * dx + dz * dz, 0.000001)
        t = max(0.0, min(1.0, ((x - a[0]) * dx + (z - a[1]) * dz) / length))
        return math.hypot(x - a[0] - t * dx, z - a[1] - t * dz)

    def blocked(self, x: float, z: float, y: float) -> bool:
        if not self.in_bounds(x, z):
            return True
        attrs = self._attrs
        z_min = max(0, math.floor(z - PLAYER_RADIUS))
        z_max = math.floor(z + PLAYER_RADIUS)
        x_min = max(0, math.floor(x - PLAYER_RADIUS))
        x_max = math.floor(x + PLAYER_RADIUS)
        for az in range(z_min, z_max + 1):
            row = az * self.width
            for ax in range(x_min, x_max + 1):
                near_x = min(max(x, float(ax)), float(ax) + 1.0)
                near_z = min(max(z, float(az)), float(az) + 1.0)
                if math.hypot(x - near_x, z - near_z) >= PLAYER_RADIUS:
                    continue
                flags = attrs[row + ax]
                if flags & 1 != 0:
                    return True
                if flags & 2 != 0 and y <= self._terrain(ax // 2, az // 2) + 0.4:
                    return True
        for shape in self._shape_tiles.get((math.floor(x / TILE_M), math.floor(z / TILE_M)), ()):
            if y + 1.6 <= shape[1] or y + 0.3 >= shape[2]:
                continue
            if shape[0] > 0.5:
                if math.hypot(x - shape[3], z - shape[4]) < shape[11] + PLAYER_RADIUS:
                    return True
                continue
            positive = False
            negative = False
            for i in range(4):
                j = (i + 1) % 4
                a = (shape[3 + i * 2], shape[4 + i * 2])
                b = (shape[3 + j * 2], shape[4 + j * 2])
                if self._segment_distance(x, z, a, b) < PLAYER_RADIUS:
                    return True
                cross = (b[0] - a[0]) * (z - a[1]) - (b[1] - a[1]) * (x - a[0])
                positive |= cross > 0.001
                negative |= cross < -0.001
            if positive != negative:
                return True
        return False

    def standable(self, x: float, z: float) -> bool:
        key = (round(x, 3), round(z, 3))
        cached = self._standable_cache.get(key)
        if cached is not None:
            return cached
        value = self.in_bounds(key[0], key[1]) and not self.blocked(
            key[0], key[1], self.height(key[0], key[1])
        )
        if len(self._standable_cache) < 2_000_000:
            self._standable_cache[key] = value
        return value

    def clear_path(self, x: float, z: float, tx: float, tz: float) -> bool:
        if not self.in_bounds(x, z) or not self.in_bounds(tx, tz):
            return False
        count = max(1, math.ceil(math.hypot(tx - x, tz - z) / 0.25))
        for i in range(count + 1):
            t = i / count
            px = x + (tx - x) * t
            pz = z + (tz - z) * t
            if self.blocked(px, pz, self.height(px, pz)):
                return False
        return True

    def plan(
        self, start: tuple[float, float], goal: tuple[float, float], *, step: float = STEP_M
    ) -> list[tuple[float, float]]:
        """A* over the walkable grid, simplified to clear straight segments."""
        start_cell = (round(start[0] / step), round(start[1] / step))
        goal_cell = _nearest_standable_cell(self, goal, step)
        if goal_cell is None:
            raise ValueError("The requested destination has no standable cell.")
        points = _search(self, start_cell, goal_cell, step)
        grid_points = [(cx * step, cz * step) for cx, cz in points]
        grid_points[0] = (start[0], start[1])
        grid_points[-1] = (goal[0], goal[1])
        return _simplify(self, grid_points)

    def anchor(self, npc: tuple[float, float], toward: tuple[float, float]) -> tuple[float, float]:
        """Pick a standable interaction point with a clear line of sight to the NPC."""
        bearing = math.atan2(toward[1] - npc[1], toward[0] - npc[0])
        for radius in (2.4, 1.8, 3.2, 4.0, 1.2, 4.6):
            for offset in (0.0, 0.35, -0.35, 0.7, -0.7, 1.05, -1.05):
                angle = bearing + offset
                x = npc[0] + math.cos(angle) * radius
                z = npc[1] + math.sin(angle) * radius
                if not self.standable(x, z):
                    continue
                if abs(self.height(x, z) - self.height(npc[0], npc[1])) > 3.0:
                    continue
                if not self.clear_path(x, z, npc[0], npc[1]):
                    continue
                if not self.clear_path(npc[0], npc[1], x, z):
                    continue
                return (x, z)
        raise ValueError("No clear interaction point was found for that NPC.")


def _tiles_for_box(
    box: tuple[float, float, float, float], pad: float = 0.0
) -> list[tuple[int, int]]:
    """Tile keys whose 16 m cell overlaps the axis-aligned box."""
    min_x = math.floor((box[0] - pad) / TILE_M)
    max_x = math.floor((box[1] + pad) / TILE_M)
    min_z = math.floor((box[2] - pad) / TILE_M)
    max_z = math.floor((box[3] + pad) / TILE_M)
    return [(tx, tz) for tx in range(min_x, max_x + 1) for tz in range(min_z, max_z + 1)]


def _nearest_standable_cell(
    world: World, point: tuple[float, float], step: float
) -> tuple[int, int] | None:
    base = (round(point[0] / step), round(point[1] / step))
    for ring in range(0, 12):
        for dz in range(-ring, ring + 1):
            for dx in range(-ring, ring + 1):
                if max(abs(dx), abs(dz)) != ring:
                    continue
                cell = (base[0] + dx, base[1] + dz)
                if world.standable(cell[0] * step, cell[1] * step):
                    return cell
    return None


def _search(
    world: World,
    start: tuple[int, int],
    goal: tuple[int, int],
    step: float,
    *,
    limit: int = 400_000,
) -> list[tuple[int, int]]:
    neighbours = (
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
    )
    open_heap: list[tuple[float, tuple[int, int]]] = [(0.0, start)]
    came: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    cost: dict[tuple[int, int], float] = {start: 0.0}
    visited = 0
    while open_heap and visited < limit:
        _, current = heapq.heappop(open_heap)
        if current == goal:
            path = [current]
            while came[current] is not None:
                current = came[current]  # type: ignore[assignment]
                path.append(current)
            path.reverse()
            return path
        visited += 1
        for dx, dz in neighbours:
            cell = (current[0] + dx, current[1] + dz)
            if cell in came:
                continue
            if not world.standable(cell[0] * step, cell[1] * step):
                continue
            if dx and dz:
                if not world.standable((current[0] + dx) * step, current[1] * step):
                    continue
                if not world.standable(current[0] * step, (current[1] + dz) * step):
                    continue
            move = step * (math.sqrt(2.0) if dx and dz else 1.0)
            candidate = cost[current] + move
            if candidate >= cost.get(cell, math.inf):
                continue
            cost[cell] = candidate
            came[cell] = current
            heuristic = step * max(abs(cell[0] - goal[0]), abs(cell[1] - goal[1]))
            heapq.heappush(open_heap, (candidate + heuristic, cell))
    raise ValueError(f"No walkable route was found within {limit} cells.")


def _simplify(world: World, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) <= 2:
        return points
    result = [points[0]]
    index = 0
    while index < len(points) - 1:
        step = len(points) - 1
        while step > index + 1:
            if world.clear_path(*points[index], *points[step]):
                break
            step -= 1
        result.append(points[step])
        index = step
    return result


def parse_point(value: str) -> tuple[float, float]:
    parts = value.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("Points are written as X,Z.")
    return (float(parts[0]), float(parts[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--from", dest="start", type=parse_point, required=True)
    parser.add_argument("--to", dest="goal", type=parse_point, required=True)
    parser.add_argument("--step", type=float, default=STEP_M)
    parser.add_argument("--check", action="store_true", help="Verify height and clearance")
    arguments = parser.parse_args()
    world = World.load(arguments.world)
    route = world.plan(arguments.start, arguments.goal, step=arguments.step)
    if arguments.check:
        for index in range(1, len(route)):
            if not world.clear_path(*route[index - 1], *route[index]):
                raise SystemExit(f"segment {index - 1}->{index} is not clear")
        if not world.standable(*arguments.goal):
            raise SystemExit("destination is not standable")
    print(
        json_dumps(
            {
                "start": list(arguments.start),
                "goal": list(arguments.goal),
                "goal_height": world.height(*arguments.goal),
                "waypoints": [[round(x, 3), round(z, 3)] for x, z in route],
            }
        )
    )


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value, indent=2)


if __name__ == "__main__":
    main()
