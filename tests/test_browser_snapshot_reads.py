import json
import math
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.browser_snapshot import SnapshotUnavailableError, read_fresh_json_snapshot


class FreshSnapshotReadTests(unittest.TestCase):
    def test_partial_write_recovers_with_a_fresh_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "desktop.json"
            path.write_text('{"connection_state":', encoding="utf-8")
            expected = {"connection_state": "connected", "monsters": []}
            partial_read = threading.Event()
            real_read_text = Path.read_text

            def observed_read(candidate: Path, *args, **kwargs) -> str:
                value = real_read_text(candidate, *args, **kwargs)
                if candidate == path and value == '{"connection_state":':
                    partial_read.set()
                return value

            def finish_write() -> None:
                if not partial_read.wait(timeout=1):
                    return
                path.write_text(json.dumps(expected), encoding="utf-8")

            writer = threading.Thread(target=finish_write)
            writer.start()
            try:
                with patch.object(Path, "read_text", observed_read):
                    snapshot, attempts, _elapsed = read_fresh_json_snapshot(
                        path, timeout=0.3, interval=0.005
                    )
            finally:
                writer.join(timeout=1)

        self.assertFalse(writer.is_alive())
        self.assertEqual(snapshot, expected)
        self.assertGreater(attempts, 1)

    def test_persistent_missing_and_malformed_snapshots_time_out_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            malformed = directory_path / "malformed.json"
            malformed.write_text('{"connection_state":', encoding="utf-8")
            missing = directory_path / "missing.json"

            for path, reason in [(malformed, "JSONDecodeError"), (missing, "FileNotFoundError")]:
                with self.subTest(path=path.name):
                    with self.assertRaises(SnapshotUnavailableError) as raised:
                        read_fresh_json_snapshot(path, timeout=0.03, interval=0.005)
                    self.assertGreater(raised.exception.attempts, 1)
                    self.assertGreaterEqual(raised.exception.elapsed, 0.025)
                    self.assertIn(reason, raised.exception.reason)
                    self.assertIn("Native snapshot unavailable", str(raised.exception))

    def test_genuine_empty_monster_list_is_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "desktop.json"
            expected = {"connection_state": "connected", "monsters": []}
            path.write_text(json.dumps(expected), encoding="utf-8")

            snapshot, attempts, _elapsed = read_fresh_json_snapshot(
                path, timeout=0.03, interval=0.005
            )

        self.assertEqual(snapshot, expected)
        self.assertEqual(attempts, 1)

    def test_empty_object_is_unavailable_instead_of_an_empty_world(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "desktop.json"
            path.write_text("{}", encoding="utf-8")

            with self.assertRaises(SnapshotUnavailableError) as raised:
                read_fresh_json_snapshot(path, timeout=0, interval=0.005)

        self.assertEqual(raised.exception.attempts, 1)
        self.assertIn("nonempty JSON object", raised.exception.reason)

    def test_retry_bounds_must_be_finite_and_ordered(self):
        path = Path("unused.json")
        for timeout, interval in [
            (-0.01, 0.005),
            (math.inf, 0.005),
            (math.nan, 0.005),
            (0.03, 0.0),
            (0.03, -0.005),
            (0.03, math.inf),
            (0.03, math.nan),
        ]:
            with self.subTest(timeout=timeout, interval=interval):
                with self.assertRaisesRegex(ValueError, "must be finite"):
                    read_fresh_json_snapshot(path, timeout=timeout, interval=interval)


if __name__ == "__main__":
    unittest.main()
