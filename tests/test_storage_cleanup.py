from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.storage_cleanup import (
    MANIFEST_VERSION,
    apply_entry_deletions,
    build_manifest,
    build_snapshot,
    classify,
    load_manifest,
    owned_names,
    parse_args,
    parse_owned_names,
    plan_entries,
    probe_database,
    read_replica_identities,
    remove_manifest_files,
    retention_reason,
    run_files,
    stop_standalone_server,
)

IDENTITY_A = "a" * 64
IDENTITY_B = "b" * 64


class StorageCleanupFixture(unittest.TestCase):
    """A throwaway standalone data directory with a server log and replicas."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data_dir = Path(self.temporary.name) / "server"
        (self.data_dir / "logs").mkdir(parents=True)
        (self.data_dir / "replicas").mkdir()

    @property
    def log_path(self) -> Path:
        return self.data_dir / "logs/spacetime-standalone.log"

    def write_log(self, text: str) -> None:
        self.log_path.write_text(text)

    def replica(self, name: str, files: dict[str, int] | None = None) -> Path:
        path = self.data_dir / "replicas" / name
        path.mkdir(parents=True, exist_ok=True)
        for filename, size in (files or {"db.lock": 4}).items():
            (path / filename).write_bytes(b"\0" * size)
        return path


def launch_line(identity: str, replica: str) -> str:
    return f"INFO: launching module db={identity} replica={replica}"


def lock_line(directory: str) -> str:
    return f"INFO: Acquired lock on /srv/data/replicas/{directory}/db.lock"


def row(
    directory: str,
    *,
    size: int = 1000,
    age_days: float = 5.0,
    names: list[str] | None = None,
    identity: str | None = IDENTITY_A,
    attached: bool | None = None,
) -> dict:
    return {
        "dir": directory,
        "path": f"/data/replicas/{directory}",
        "bytes": size,
        "age_days": age_days,
        "identity": identity,
        "names": list(names or []),
        "attached": attached,
    }


class IdentityMappingTests(StorageCleanupFixture):
    def test_launch_records_directory_and_later_launch_wins(self) -> None:
        self.write_log(
            "\n".join(
                [
                    launch_line(IDENTITY_A, "7"),
                    launch_line(IDENTITY_B, "7"),
                    launch_line(IDENTITY_A, "11"),
                    "",
                ]
            )
        )
        self.assertEqual(
            read_replica_identities(self.data_dir), {"7": IDENTITY_B, "11": IDENTITY_A}
        )

    def test_pending_launch_is_resolved_by_the_next_lock(self) -> None:
        self.write_log("\n".join([launch_line(IDENTITY_B, "0"), lock_line("9"), ""]))
        self.assertEqual(read_replica_identities(self.data_dir), {"9": IDENTITY_B})

    def test_missing_log_reports_no_mapping(self) -> None:
        self.assertFalse(read_replica_identities(self.data_dir))

    def test_unpaired_pending_launch_is_not_guessed(self) -> None:
        self.write_log(launch_line(IDENTITY_B, "0") + "\n")
        self.assertEqual(read_replica_identities(self.data_dir), {})


class ParseOwnedNamesTests(unittest.TestCase):
    def test_names_and_identity_are_split_per_line(self) -> None:
        output = "\n".join(
            [
                f"mt2-p1, mt2-p1-final | {IDENTITY_A}",
                f"mt2-p2-quests-r6-20260910 | {IDENTITY_B}",
                f"other-project | {IDENTITY_A}",
                "mt2-p3-broken | not-an-identity",
                "no separator here",
                "",
            ]
        )
        self.assertEqual(
            parse_owned_names(output),
            {
                "mt2-p1": IDENTITY_A,
                "mt2-p1-final": IDENTITY_A,
                "mt2-p2-quests-r6-20260910": IDENTITY_B,
            },
        )

    def test_cli_failure_is_reported(self) -> None:
        def failing_runner(command: list[str]) -> tuple[int, str]:
            self.assertIn("list", command)
            return 2, "no server"

        with self.assertRaises(RuntimeError):
            owned_names("spacetime", "http://127.0.0.1:1", Path("/nonexistent"), failing_runner)


class ProbeTests(unittest.TestCase):
    def probe(self, code: int, output: str) -> bool | None:
        seen: list[list[str]] = []

        def runner(command: list[str]) -> tuple[int, str]:
            seen.append(command)
            return code, output

        result = probe_database(
            "spacetime", "http://127.0.0.1:13223", Path("/nonexistent"), IDENTITY_A, runner
        )
        self.assertIn("describe", seen[0])
        self.assertIn(IDENTITY_A, seen[0])
        return result

    def test_attached_entry(self) -> None:
        self.assertIs(self.probe(0, "database: mt2-p1"), True)

    def test_detached_entry(self) -> None:
        self.assertIs(self.probe(1, "error: No such database: abc"), False)
        self.assertIs(self.probe(1, "HTTP 404 Not Found"), False)

    def test_inconclusive_probe(self) -> None:
        self.assertIsNone(self.probe(1, "connection refused"))


class RetentionTests(StorageCleanupFixture):
    def test_recent_directory_is_retained(self) -> None:
        self.assertEqual(
            retention_reason(row("7", age_days=1.0), 2.0, ["mt2-p1"]), "active within 2 days"
        )

    def test_keep_pattern_protects_old_database(self) -> None:
        self.assertEqual(
            retention_reason(row("7", names=["mt2-p1"]), 2.0, ["mt2-p1"]),
            "matches keep pattern for mt2-p1",
        )

    def test_old_unnamed_directory_is_obsolete(self) -> None:
        self.assertIsNone(retention_reason(row("7"), 2.0, ["mt2-p1"]))

    def test_classify_splits_owned_orphan_and_other_identities(self) -> None:
        rows = [
            row("1", age_days=9.0, names=["mt2-p1-qa"], identity=IDENTITY_A),
            row("2", age_days=9.0, names=[], identity=IDENTITY_A, attached=True),
            row("3", age_days=9.0, names=[], identity=IDENTITY_A, attached=False),
            row("4", age_days=9.0, names=[], identity=None),
            row("5", age_days=0.5, names=[], identity=IDENTITY_A, attached=False),
        ]
        classify({"replicas": rows}, 2.0, ["mt2-p1"])
        self.assertTrue(rows[0]["obsolete_named"])
        self.assertTrue(rows[1]["unattached"])
        self.assertFalse(rows[1]["orphan"])
        self.assertTrue(rows[2]["orphan"])
        self.assertTrue(rows[3]["unknown_identity"])
        self.assertFalse(rows[3]["orphan"])
        self.assertEqual(rows[4]["retained"], "active within 2 days")
        self.assertFalse(rows[4]["orphan"])


class EntryPlanTests(unittest.TestCase):
    def test_only_owned_obsolete_names_are_planned(self) -> None:
        rows = [
            row("1", age_days=9.0, names=["mt2-p1-qa"], identity=IDENTITY_A),
            row("2", age_days=9.0, names=["other-db"], identity=IDENTITY_B),
            row("3", age_days=0.5, names=["mt2-p1-recent"], identity=IDENTITY_A),
        ]
        classify({"replicas": rows}, 2.0, ["mt2-p1"])
        planned, unowned = plan_entries(rows, {"mt2-p1-qa": IDENTITY_A})
        self.assertEqual([record["name"] for record in planned], ["mt2-p1-qa"])
        self.assertEqual([record["name"] for record in unowned], ["other-db"])
        self.assertEqual(planned[0]["dir"], "1")

    def test_delete_commands_carry_the_server_and_confirmation(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str]) -> tuple[int, str]:
            commands.append(command)
            return (0, "deleted") if "good-db" in command else (1, "boom")

        records = [
            {"name": "good-db", "identity": IDENTITY_A, "dir": "1", "bytes": 10},
            {"name": "bad-db", "identity": IDENTITY_A, "dir": "2", "bytes": 10},
        ]
        result = apply_entry_deletions(
            records, "spacetime", "http://srv", Path("/nonexistent"), True, runner
        )
        self.assertEqual([record["name"] for record in result["deleted"]], ["good-db"])
        self.assertEqual([record["name"] for record in result["failed"]], ["bad-db"])
        self.assertIn("boom", result["failed"][0]["error"])
        self.assertEqual(commands[0][1:3], ["delete", "--server"])
        self.assertIn("-y", commands[0])

    def test_dry_run_never_calls_the_cli(self) -> None:
        def runner(command: list[str]) -> tuple[int, str]:
            raise AssertionError("dry run must not run the CLI")

        records = [{"name": "db", "identity": IDENTITY_A, "dir": "1", "bytes": 10}]
        result = apply_entry_deletions(
            records, "spacetime", "http://srv", Path("/nonexistent"), False, runner
        )
        self.assertFalse(result["applied"])
        self.assertEqual(len(result["deleted"]), 1)


class ManifestTests(StorageCleanupFixture):
    def test_manifest_round_trip_records_entries_and_bytes(self) -> None:
        snapshot = {"data_dir": str(self.data_dir)}
        deleted = [{"name": "db", "identity": IDENTITY_A, "dir": "7", "bytes": 5}]
        orphans = [{"name": None, "identity": IDENTITY_B, "dir": "9", "bytes": 7}]
        manifest = build_manifest(snapshot, "http://srv", deleted, orphans)
        self.assertEqual(manifest["version"], MANIFEST_VERSION)
        self.assertEqual([entry["dir"] for entry in manifest["entries"]], ["7", "9"])
        self.assertEqual(
            [entry["source"] for entry in manifest["entries"]], ["detached-entry", "orphan-probe"]
        )
        self.assertEqual(manifest["planned_bytes"], 12)
        path = self.data_dir / "manifest.json"
        path.write_text(json.dumps(manifest))
        self.assertEqual(load_manifest(path)["entries"], manifest["entries"])

    def test_missing_or_future_manifest_is_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            load_manifest(self.data_dir / "absent.json")
        path = self.data_dir / "future.json"
        path.write_text(json.dumps({"version": MANIFEST_VERSION + 1, "entries": []}))
        with self.assertRaises(RuntimeError):
            load_manifest(path)


class RemoveFilesGuardTests(StorageCleanupFixture):
    def manifest(self, record: dict) -> dict:
        return {"version": MANIFEST_VERSION, "data_dir": str(self.data_dir), "entries": [record]}

    def test_successful_removal_counts_bytes(self) -> None:
        directory = self.replica("7", {"db.lock": 4, "log": 6})
        self.write_log(launch_line(IDENTITY_A, "7") + "\n")
        manifest = self.manifest({"name": "db", "identity": IDENTITY_A, "dir": "7", "bytes": 10})
        result = remove_manifest_files(manifest, self.data_dir, set(), apply=True)
        self.assertEqual(result["freed"], 10)
        self.assertEqual(len(result["removed"]), 1)
        self.assertFalse(directory.exists())

    def test_dry_run_keeps_every_directory(self) -> None:
        directory = self.replica("7")
        self.write_log(launch_line(IDENTITY_A, "7") + "\n")
        manifest = self.manifest({"name": "db", "identity": IDENTITY_A, "dir": "7", "bytes": 4})
        result = remove_manifest_files(manifest, self.data_dir, set(), apply=False)
        self.assertTrue(directory.is_dir())
        self.assertEqual(result["removed"][0]["bytes"], 4)

    def test_reused_directory_is_refused_when_owner_changed(self) -> None:
        self.replica("7")
        self.write_log(launch_line(IDENTITY_A, "7") + "\n" + launch_line(IDENTITY_B, "7") + "\n")
        manifest = self.manifest({"identity": IDENTITY_A, "dir": "7", "bytes": 4})
        result = remove_manifest_files(manifest, self.data_dir, set(), apply=True)
        self.assertEqual(result["removed"], [])
        self.assertIn("directory now belongs to", result["skipped"][0]["reason"])

    def test_live_identity_is_never_removed(self) -> None:
        self.replica("7")
        self.write_log(launch_line(IDENTITY_A, "7") + "\n")
        manifest = self.manifest({"identity": IDENTITY_A, "dir": "7", "bytes": 4})
        result = remove_manifest_files(manifest, self.data_dir, {IDENTITY_A}, apply=True)
        self.assertIn("still attached", result["skipped"][0]["reason"])

    def test_unknown_owner_and_path_traversal_are_skipped(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (outside / "db.lock").write_bytes(b"\0" * 4)
        self.write_log(launch_line(IDENTITY_A, "8") + "\n")
        manifest = {
            "version": MANIFEST_VERSION,
            "data_dir": str(self.data_dir),
            "entries": [
                {"identity": IDENTITY_A, "dir": "9", "bytes": 1},
                {"identity": IDENTITY_A, "dir": "../outside", "bytes": 4},
                {"identity": IDENTITY_A, "dir": "8", "bytes": 4},
            ],
        }
        result = remove_manifest_files(manifest, self.data_dir, set(), apply=True)
        reasons = [record["reason"] for record in result["skipped"]]
        self.assertIn("no server-log owner recorded", reasons[0])
        self.assertIn("not a numeric replica directory", reasons[1])
        self.assertIn("already gone", result["skipped"][2]["reason"])
        self.assertTrue(outside.is_dir())


class SnapshotTests(StorageCleanupFixture):
    def test_probe_only_asks_about_unnamed_identities(self) -> None:
        self.replica("7", {"db.lock": 4})
        self.replica("9", {"db.lock": 4, "wal": 8})
        self.write_log(launch_line(IDENTITY_A, "7") + "\n" + launch_line(IDENTITY_B, "9") + "\n")
        probed: list[str] = []

        def probe(identity: str) -> bool:
            probed.append(identity)
            return False

        snapshot = build_snapshot(self.data_dir, {"mt2-p1": IDENTITY_A}, probe)
        self.assertEqual(probed, [IDENTITY_B])
        self.assertEqual(snapshot["total_bytes"], 16)
        rows = {entry["dir"]: entry for entry in snapshot["replicas"]}
        self.assertEqual(rows["7"]["names"], ["mt2-p1"])
        self.assertIsNone(rows["7"]["attached"])
        self.assertIs(rows["9"]["attached"], False)

    def test_offline_snapshot_does_not_probe(self) -> None:
        self.replica("7")
        self.write_log(launch_line(IDENTITY_A, "7") + "\n")
        snapshot = build_snapshot(self.data_dir, None, None)
        self.assertFalse(snapshot["names_available"])
        self.assertEqual(snapshot["replicas"][0]["identity"], IDENTITY_A)
        self.assertEqual(snapshot["replicas"][0]["names"], [])
        self.assertIsNone(snapshot["replicas"][0]["attached"])


class RunFilesTests(StorageCleanupFixture):
    def write_manifest(self, record: dict) -> Path:
        path = self.data_dir / "manifest.json"
        path.write_text(
            json.dumps(
                {"version": MANIFEST_VERSION, "data_dir": str(self.data_dir), "entries": [record]}
            )
        )
        return path

    def test_listening_server_blocks_removal_without_restart(self) -> None:
        self.replica("7")
        self.write_log(launch_line(IDENTITY_A, "7") + "\n")
        manifest = self.write_manifest({"identity": IDENTITY_A, "dir": "7", "bytes": 4})
        with mock.patch("tools.storage_cleanup.server_listening", return_value=True):
            stdout, stderr = io.StringIO(), io.StringIO()
            options = parse_args(
                [
                    "files",
                    "--manifest",
                    str(manifest),
                    "--server",
                    "http://127.0.0.1:13223",
                    "--offline",
                    "--apply",
                ]
            )
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = run_files(options)
        self.assertEqual(code, 1)
        self.assertIn("a SpacetimeDB server is listening", stderr.getvalue())
        self.assertTrue((self.data_dir / "replicas/7").is_dir())

    def test_restart_refuses_a_foreign_pid_file(self) -> None:
        self.replica("7")
        self.write_log(launch_line(IDENTITY_A, "7") + "\n")
        (self.data_dir / "spacetime.pid").write_text(str(os.getpid()))
        manifest = self.write_manifest({"identity": IDENTITY_A, "dir": "7", "bytes": 4})
        with mock.patch("tools.storage_cleanup.server_listening", return_value=True):
            options = parse_args(
                [
                    "files",
                    "--manifest",
                    str(manifest),
                    "--server",
                    "http://127.0.0.1:13223",
                    "--offline",
                    "--apply",
                    "--restart-server",
                ]
            )
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                with self.assertRaises(RuntimeError):
                    run_files(options)
        self.assertTrue((self.data_dir / "replicas/7").is_dir())

    def test_missing_data_dir_is_reported(self) -> None:
        manifest = self.data_dir / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "version": MANIFEST_VERSION,
                    "data_dir": str(self.data_dir / "gone"),
                    "entries": [],
                }
            )
        )
        stdout, stderr = io.StringIO(), io.StringIO()
        options = parse_args(["files", "--manifest", str(manifest), "--offline"])
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = run_files(options)
        self.assertEqual(code, 1)
        self.assertIn("data dir not found", stderr.getvalue())

    def test_stop_guard_rejects_unrelated_process(self) -> None:
        (self.data_dir / "spacetime.pid").write_text(str(os.getpid()))
        with self.assertRaises(RuntimeError):
            stop_standalone_server(self.data_dir, "http://127.0.0.1:1")


if __name__ == "__main__":
    unittest.main()
