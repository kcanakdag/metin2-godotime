from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/progression_operator.py"
SPEC = importlib.util.spec_from_file_location("progression_operator", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
progression_operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(progression_operator)


class ProgressionOperatorTests(unittest.TestCase):
    def test_http_origin_rejects_credentials_paths_and_queries(self) -> None:
        self.assertEqual(
            progression_operator.http_origin("http://127.0.0.1:8186/"),
            "http://127.0.0.1:8186",
        )
        for invalid in (
            "127.0.0.1:8186",
            "ftp://127.0.0.1",
            "http://user:secret@127.0.0.1",
            "http://127.0.0.1/auth",
            "http://127.0.0.1?token=secret",
        ):
            with self.assertRaises(progression_operator.OperatorError):
                progression_operator.http_origin(invalid)

    def test_credential_file_must_be_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "credentials.json"
            path.write_text(json.dumps({"username": "operator", "password": "secret"}))
            path.chmod(0o600)
            self.assertEqual(progression_operator.credentials(path), ("operator", "secret"))
            path.chmod(0o640)
            with self.assertRaises(progression_operator.OperatorError):
                progression_operator.credentials(path)

    def test_reason_file_is_private_printable_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "reason.txt"
            path.write_text("local two-account QA\n")
            path.chmod(0o600)
            self.assertEqual(progression_operator.reason_text(path), "local two-account QA")
            path.write_text("line one\nline two")
            with self.assertRaises(progression_operator.OperatorError):
                progression_operator.reason_text(path)
            path.write_text("valid reason")
            path.chmod(0o644)
            with self.assertRaises(progression_operator.OperatorError):
                progression_operator.reason_text(path)

    def test_cli_has_no_secret_argv_options(self) -> None:
        help_text = progression_operator.parser().format_help()
        self.assertNotIn("--password", help_text)
        self.assertNotIn("--username", help_text)
        self.assertNotIn("--token", help_text)
        self.assertNotIn("--reason ", help_text)
        self.assertIn("--credential-file", help_text)
        self.assertIn("--reason-file", help_text)

    def test_unshipped_driver_only_calls_structured_reducers(self) -> None:
        driver = (ROOT / "tools/progression_operator_driver.gd").read_text()
        self.assertIn('"provision_progression_operator"', driver)
        self.assertIn('"open_account"', driver)
        self.assertNotIn("execute_command", driver)
        self.assertNotIn("send_chat", driver)
        self.assertFalse((ROOT / "client/progression_operator_driver.gd").exists())

    def test_private_json_rejects_non_object(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "value.json"
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as handle:
                json.dump(["not", "an", "object"], handle)
            with self.assertRaises(progression_operator.OperatorError):
                progression_operator.private_json(path, "fixture")

    def test_failed_second_invocation_replaces_stale_success_report(self) -> None:
        target = "12" * 32
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            credentials = directory / "credentials.json"
            credentials.write_text(json.dumps({"username": "operator", "password": "secret"}))
            credentials.chmod(0o644)
            report = directory / "report.json"
            progression_operator.atomic_report(
                report,
                {"run_id": "old", "request_id": "old", "applied": True, "status": "applied"},
            )
            arguments = [
                str(MODULE_PATH),
                "grant",
                target,
                "--database",
                "mt2-p2-fixture",
                "--credential-file",
                str(credentials),
                "--report",
                str(report),
            ]
            with (
                mock.patch("sys.argv", arguments),
                self.assertRaises(progression_operator.OperatorError),
            ):
                progression_operator.main()
            current = json.loads(report.read_text())
            self.assertFalse(current["applied"])
            self.assertEqual(current["status"], "error")
            self.assertNotEqual(current["run_id"], "old")
            self.assertRegex(current["request_id"], r"^[0-9a-f]{32}$")
            self.assertEqual(report.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
