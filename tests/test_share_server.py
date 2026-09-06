"""Launcher ownership and failed-start cleanup, without starting a public tunnel."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import share_server as launcher  # noqa: E402


class PublicDnsTests(unittest.TestCase):
    def test_successful_public_a_record_is_ready(self) -> None:
        answer = {"Status": 0, "Answer": [{"type": 1, "data": "198.51.100.5"}]}
        with patch.object(launcher, "get_json", return_value=answer) as lookup:
            self.assertTrue(launcher.public_dns_ready("https://test.trycloudflare.com"))
        request = urlsplit(lookup.call_args.args[0])
        self.assertEqual(request.scheme, "https")
        self.assertEqual(request.hostname, "cloudflare-dns.com")
        self.assertEqual(request.path, "/dns-query")
        self.assertEqual(
            parse_qs(request.query), {"name": ["test.trycloudflare.com"], "type": ["A"]}
        )
        self.assertEqual(lookup.call_args.kwargs["accept"], "application/dns-json")

    def test_nxdomain_is_not_ready_even_with_an_answer(self) -> None:
        answer = {"Status": 3, "Answer": [{"type": 1, "data": "198.51.100.5"}]}
        with patch.object(launcher, "get_json", return_value=answer):
            self.assertFalse(launcher.public_dns_ready("https://test.trycloudflare.com"))

    def test_missing_answer_or_only_other_record_types_is_not_ready(self) -> None:
        answers = (
            {"Status": 0},
            {"Status": 0, "Answer": []},
            {"Status": 0, "Answer": [{"type": 5, "data": "target.example"}]},
            {"Status": 0, "Answer": [{"type": 28, "data": "2001:db8::5"}]},
        )
        for answer in answers:
            with (
                self.subTest(answer=answer),
                patch.object(launcher, "get_json", return_value=answer),
            ):
                self.assertFalse(launcher.public_dns_ready("https://test.trycloudflare.com"))


class OwnerTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state = Path(directory.name) / "session.json"
        state_patch = patch.object(launcher, "STATE", self.state)
        state_patch.start()
        self.addCleanup(state_patch.stop)
        self.value = {
            "status": "ready",
            "owner_pid": os.getpid(),
            "owner_start": launcher.process_start(os.getpid()),
            "database": "launcher-test",
        }
        self.arguments = [sys.executable, str(Path(launcher.__file__).resolve()), "start"]

    def inspect(self, **options) -> dict:
        self.state.write_text(json.dumps(self.value))
        command = ("\0".join(self.arguments) + "\0").encode()
        with patch.object(Path, "read_bytes", return_value=command):
            return launcher.active_state(**options)

    def test_expected_launcher_with_matching_start_time_is_accepted(self) -> None:
        self.assertEqual(self.inspect(), self.value)

    def test_reused_pid_with_different_start_time_is_rejected(self) -> None:
        self.value["owner_start"] = "definitely-not-this-process-start"
        with self.assertRaises(RuntimeError):
            self.inspect()

    def test_different_script_is_rejected(self) -> None:
        self.arguments[1] = "/tmp/another-project/tools/share_server.py"
        with self.assertRaises(RuntimeError):
            self.inspect()

    def test_stopped_session_is_rejected(self) -> None:
        self.value["status"] = "stopped"
        with self.assertRaises(RuntimeError):
            self.inspect()

    def test_starting_session_is_rejected_by_default(self) -> None:
        self.value["status"] = "starting"
        with self.assertRaises(RuntimeError):
            self.inspect()

    def test_verified_starting_session_can_be_requested_for_stop(self) -> None:
        self.value["status"] = "starting"
        self.assertEqual(self.inspect(allow_starting=True), self.value)

    def test_allow_starting_does_not_accept_stale_owner(self) -> None:
        self.value.update(status="starting", owner_start="not-the-current-process-start")
        with self.assertRaises(RuntimeError):
            self.inspect(allow_starting=True)

    def test_script_path_in_another_process_arguments_is_rejected(self) -> None:
        # These are data passed to a harmless Python program, not its entrypoint.
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)", *self.arguments[1:]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            self.value.update(owner_pid=child.pid, owner_start=launcher.process_start(child.pid))
            self.state.write_text(json.dumps(self.value))
            with self.assertRaises(RuntimeError):
                launcher.active_state()
            self.assertIsNone(child.poll(), "Ownership inspection must not signal the process")
        finally:
            child.terminate()
            child.wait(timeout=5)


class StartupTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.local = Path(directory.name)
        self.state = self.local / "session.json"
        binary = self.local / "cloudflared"
        binary.write_bytes(b"test fixture: never executed")
        replacements = {
            "LOCAL": self.local,
            "STATE": self.state,
            "BINARY": binary,
            "DIGEST": hashlib.sha256(binary.read_bytes()).hexdigest(),
        }
        constants = patch.multiple(launcher, **replacements)
        constants.start()
        self.addCleanup(constants.stop)
        self.options = SimpleNamespace(
            database="launcher-test", server_port=0, gateway_port=0, metrics_port=0
        )
        self.gateway = Mock(pid=81001)
        self.tunnel = Mock(pid=81002)
        self.gateway.poll.return_value = None
        self.tunnel.poll.return_value = None
        self.logs = []
        self.ready_pid = self.gateway.pid
        self.spawn_error = None
        self.public_url = ""

    def spawn(self, command: list[str], **options):
        self.logs.append(options["stdout"])
        if "--ready-file" in command:
            ready_path = Path(command[command.index("--ready-file") + 1])
            ready_path.write_text(
                json.dumps({"pid": self.ready_pid, "database": self.options.database})
            )
            return self.gateway
        if self.spawn_error:
            raise self.spawn_error
        if self.public_url:
            options["stdout"].write(self.public_url + "\n")
            options["stdout"].flush()
        return self.tunnel

    def run_failed_start(self, expected_error: str) -> None:
        with (
            patch.object(launcher.subprocess, "Popen", side_effect=self.spawn),
            patch.object(launcher, "get_json", return_value={"database": self.options.database}),
            patch.object(launcher.signal, "signal", return_value=signal.SIG_DFL),
            patch.object(launcher.time, "sleep", side_effect=RuntimeError("public startup failed")),
            self.assertRaisesRegex(RuntimeError, expected_error),
        ):
            launcher.start(self.options)

    def assert_cleaned(self) -> None:
        self.assertEqual(json.loads(self.state.read_text())["status"], "stopped")
        self.assertTrue(self.logs, "The failure should exercise opened subprocess logs")
        self.assertTrue(all(log.closed for log in self.logs))
        # A following start must be able to acquire the session lock immediately.
        with (self.local / "session.lock").open("a") as lock:
            launcher.fcntl.flock(lock, launcher.fcntl.LOCK_EX | launcher.fcntl.LOCK_NB)
            launcher.fcntl.flock(lock, launcher.fcntl.LOCK_UN)

    def test_wrong_gateway_readiness_stops_owned_gateway(self) -> None:
        self.ready_pid += 1
        self.run_failed_start("readiness belongs to another process")
        self.gateway.terminate.assert_called_once()
        self.gateway.wait.assert_called_once()
        self.tunnel.terminate.assert_not_called()
        self.assert_cleaned()

    def test_tunnel_spawn_failure_stops_gateway_and_closes_both_logs(self) -> None:
        self.spawn_error = RuntimeError("cannot spawn tunnel")
        self.run_failed_start("cannot spawn tunnel")
        self.gateway.terminate.assert_called_once()
        self.gateway.wait.assert_called_once()
        self.assertEqual(len(self.logs), 2)
        self.assert_cleaned()

    def test_public_startup_failure_stops_both_children(self) -> None:
        self.run_failed_start("public startup failed")
        self.tunnel.terminate.assert_called_once()
        self.tunnel.wait.assert_called_once()
        self.gateway.terminate.assert_called_once()
        self.gateway.wait.assert_called_once()
        self.assert_cleaned()

    def test_child_exiting_during_terminate_does_not_skip_other_cleanup(self) -> None:
        self.tunnel.terminate.side_effect = ProcessLookupError("child already exited")
        self.run_failed_start("public startup failed")
        self.gateway.terminate.assert_called_once()
        self.gateway.wait.assert_called_once()
        self.assert_cleaned()

    def test_unresponsive_child_is_killed_and_reaped(self) -> None:
        self.tunnel.wait.side_effect = [subprocess.TimeoutExpired("cloudflared", 5), 0]
        self.run_failed_start("public startup failed")
        self.tunnel.kill.assert_called_once()
        self.assertEqual(self.tunnel.wait.call_count, 2)
        self.gateway.terminate.assert_called_once()
        self.assert_cleaned()

    def test_child_exiting_before_forced_kill_does_not_skip_other_cleanup(self) -> None:
        self.tunnel.wait.side_effect = [subprocess.TimeoutExpired("cloudflared", 5), 0]
        self.tunnel.kill.side_effect = ProcessLookupError("child already exited")
        self.run_failed_start("public startup failed")
        self.tunnel.kill.assert_called_once()
        self.assertEqual(self.tunnel.wait.call_count, 2)
        self.gateway.terminate.assert_called_once()
        self.gateway.wait.assert_called_once()
        self.assert_cleaned()

    def test_public_health_waits_until_dns_preflight_becomes_positive(self) -> None:
        self.public_url = "https://launcher-test.trycloudflare.com"
        checks = []
        dns_positive = False

        def response(url: str, **_options) -> dict:
            nonlocal dns_positive
            hostname = urlsplit(url).hostname
            if hostname == "cloudflare-dns.com":
                if not checks:
                    checks.append("dns-negative")
                    return {"Status": 3}
                checks.append("dns-positive")
                dns_positive = True
                return {"Status": 0, "Answer": [{"type": 1, "data": "198.51.100.5"}]}
            if hostname == "launcher-test.trycloudflare.com":
                self.assertTrue(dns_positive, "Public health would resolve unpublished DNS")
                self.assertEqual(url, self.public_url + "/health")
                checks.append("public-health")
            else:
                self.assertEqual(hostname, "127.0.0.1")
            return {"database": self.options.database}

        with (
            patch.object(launcher.subprocess, "Popen", side_effect=self.spawn),
            patch.object(launcher, "get_json", side_effect=response),
            patch.object(launcher.signal, "signal", return_value=signal.SIG_DFL),
            patch.object(launcher.time, "sleep", side_effect=[None, KeyboardInterrupt]),
        ):
            launcher.start(self.options)
        self.assertEqual(checks, ["dns-negative", "dns-positive", "public-health"])
        self.assertEqual(json.loads(self.state.read_text())["server_url"], self.public_url)
        self.assert_cleaned()


if __name__ == "__main__":
    unittest.main()
