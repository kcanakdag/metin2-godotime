"""Pure helpers for interpreting browser/native development snapshots."""

from __future__ import annotations

import math

POSITION_VALID = "valid"
POSITION_PENDING = "pending"
POSITION_INVALID = "invalid"


def subscribed_player_position(snapshot: dict, identity: str) -> tuple[str, list[float] | None]:
    """Return the authoritative online player's subscribed row position and its status."""
    rows = snapshot.get("player_rows")
    if not isinstance(rows, list):
        return POSITION_PENDING, None
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("identity") == identity and row.get("online") is True
    ]
    if not matches:
        return POSITION_PENDING, None
    if len(matches) != 1:
        return POSITION_INVALID, None
    values = [matches[0].get(axis) for axis in ("x", "y", "z")]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        return POSITION_INVALID, None
    position = [float(value) for value in values]
    if not all(math.isfinite(value) for value in position):
        return POSITION_INVALID, None
    return POSITION_VALID, position


def authoritative_position_distance(first: list[float], second: list[float]) -> float:
    """Measure authoritative position drift across all three spatial axes."""
    return math.dist(first, second)
