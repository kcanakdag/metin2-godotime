"""Pure helpers for interpreting browser/native development snapshots."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

POSITION_VALID = "valid"
POSITION_PENDING = "pending"
POSITION_INVALID = "invalid"
NATIVE_SNAPSHOT_READ_TIMEOUT = 0.75
NATIVE_SNAPSHOT_READ_INTERVAL = 0.01


class SnapshotUnavailableError(RuntimeError):
    """A probe snapshot did not become readable within the bounded retry window."""

    def __init__(self, path: Path, attempts: int, elapsed: float, reason: str) -> None:
        self.attempts = attempts
        self.elapsed = elapsed
        self.reason = reason
        super().__init__(
            f"Native snapshot unavailable after {attempts} fresh reads over "
            f"{elapsed:.3f}s ({path}: {reason})"
        )


def read_fresh_json_snapshot(
    path: Path,
    *,
    timeout: float = NATIVE_SNAPSHOT_READ_TIMEOUT,
    interval: float = NATIVE_SNAPSHOT_READ_INTERVAL,
) -> tuple[dict, int, float]:
    """Read one complete probe snapshot without substituting an empty world.

    Current exports atomically replace complete snapshots. Older exports wrote
    in place; startup and those older writers can briefly expose missing, empty,
    or partial JSON. Retry fresh reads for a bounded interval, then expose
    unavailability as an error. A nonempty parsed snapshot remains authoritative even when one of
    its subscribed tables, such as ``monsters``, is genuinely empty.
    """
    if not math.isfinite(timeout) or not math.isfinite(interval) or timeout < 0 or interval <= 0:
        raise ValueError(
            "Snapshot read timeout must be finite and nonnegative and interval positive"
        )
    started = time.monotonic()
    deadline = started + timeout
    attempts = 0
    reason = "no read attempted"
    while True:
        attempts += 1
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(snapshot, dict) or not snapshot:
                raise ValueError("snapshot must be a nonempty JSON object")
            return snapshot, attempts, time.monotonic() - started
        except (OSError, ValueError) as error:
            reason = f"{type(error).__name__}: {error}"
        now = time.monotonic()
        if now >= deadline:
            raise SnapshotUnavailableError(path, attempts, now - started, reason)
        time.sleep(min(interval, deadline - now))


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
