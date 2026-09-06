"""Artifact integrity, package exclusions, and deployment recovery without remote services."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import export_client  # noqa: E402

import deploy  # noqa: E402


class WebArtifactTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for name in ["index.html", "index.js", "index.wasm", "index.pck", "world/section.pck"]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"export fixture")
        self.manifest = {
            "target": "web",
            "test_probe": False,
            "pack_audit": {"files_checked": 42, "test_probe_present": False},
            "files": {
                p.relative_to(self.root).as_posix(): {
                    "bytes": p.stat().st_size,
                    "sha256": deploy.digest(p),
                }
                for p in self.root.rglob("*")
                if p.is_file()
            },
        }
        self.save_manifest()

    def save_manifest(self):
        (self.root / deploy.MANIFEST).write_text(json.dumps(self.manifest))

    def test_complete_recursive_artifact_is_accepted(self):
        self.assertEqual(deploy.validate_web_build(self.root), self.manifest)

    def test_changed_streamed_pack_is_rejected_even_if_size_matches(self):
        (self.root / "world/section.pck").write_bytes(b"export changed")
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            deploy.validate_web_build(self.root)

    def test_untracked_secret_file_is_rejected(self):
        (self.root / "session-token.json").write_text('{"token":"private fixture"}')
        with self.assertRaisesRegex(ValueError, "every published file"):
            deploy.validate_web_build(self.root)

    def test_missing_streamed_pack_is_rejected(self):
        (self.root / "world/section.pck").unlink()
        with self.assertRaisesRegex(ValueError, "every published file"):
            deploy.validate_web_build(self.root)

    def test_symbolic_link_cannot_publish_outside_file(self):
        (self.root / "linked-config").symlink_to("/etc/passwd")
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            deploy.validate_web_build(self.root)

    def test_test_build_requires_opt_in_and_matching_pack_audit(self):
        self.manifest["test_probe"] = True
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "explicit --allow-test-build"):
            deploy.validate_web_build(self.root)
        with self.assertRaisesRegex(ValueError, "inconsistent actual-PCK audit"):
            deploy.validate_web_build(self.root, allow_test_build=True)
        self.manifest["pack_audit"]["test_probe_present"] = True
        self.save_manifest()
        self.assertTrue(deploy.validate_web_build(self.root, allow_test_build=True)["test_probe"])


class PackExclusionTests(unittest.TestCase):
    def test_runtime_sdk_auth_code_is_allowed(self):
        result = export_client.validate_pack_paths(
            ["res://addons/SpacetimeDB/util/jwt_helper.gdc", "res://.godot/imported/warrior.scn"]
        )
        self.assertFalse(result["test_probe_present"])
        self.assertEqual(result["files_checked"], 2)

    def test_private_files_source_archives_and_bridges_are_rejected(self):
        for path in [
            "res://addons/godot_mcp/services/mcp_runtime_bridge.gdc",
            "res://addons/mt2_dev_bridge/evaluator.gdc",
            "res://identities/alice.json",
            "res://assets/source/model.gr2",
            "res://saved/issuer.pem",
            "res://logs/client.log",
            "res://.env.production",
            "res://tests/multiplayer_smoke.gdc",
        ]:
            with self.subTest(path=path), self.assertRaisesRegex(RuntimeError, "Forbidden"):
                export_client.validate_pack_paths([path])

    def test_compiled_probe_requires_opt_in_and_is_required_when_requested(self):
        path = "res://scripts/export_probe.gdc"
        with self.assertRaisesRegex(RuntimeError, "Test probe included"):
            export_client.validate_pack_paths([path])
        self.assertTrue(
            export_client.validate_pack_paths([path], allow_test_probe=True)["test_probe_present"]
        )
        with self.assertRaisesRegex(RuntimeError, "no packaged test probe"):
            export_client.validate_pack_paths([], allow_test_probe=True)


# Execute the real shell workflow against command stand-ins. Only the fixed repository/VPS paths
# are relocated to temporary storage; no Docker daemon, network, certificates, or root is used.
COMMAND_FIXTURE = r"""#!/usr/bin/env python3
import hashlib
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["DEPLOY_TEST_ROOT"])
args = sys.argv[1:]
command = Path(sys.argv[0]).name
with (root / "commands.jsonl").open("a") as log:
    log.write(json.dumps([command, *args]) + "\n")
failure = os.environ["DEPLOY_TEST_FAILURE"]
if command in {"openssl", "ufw", "ss"}:
    sys.exit(0)
if command == "curl":
    if args[-1].endswith("/build-manifest.json"):
        sys.stdout.write((root / "web/current/build-manifest.json").read_text())
    sys.exit(0)
if command != "docker":
    raise RuntimeError("Unexpected command")
if args == ["compose", "version"]:
    print("Docker Compose fixture")
elif args == ["compose", "ps", "-aq", "db"]:
    print("previous-db")
elif args[:2] == ["inspect", "--format"]:
    print("sha256:previous-image" if args[2] == "{{.Image}}" else "metin2-godotime-db")
elif args == ["inspect", "previous-db"]:
    pass
elif args[0] == "run" and args[-2:] == ["nginx", "-t"]:
    if failure == "nginx":
        sys.exit(11)
elif args[:2] == ["stop", "previous-db"]:
    pass
elif args[:2] == ["cp", "previous-db:/data"]:
    if failure == "backup":
        sys.exit(12)
    key = Path(args[-1]) / "config/spacetime/id_ecdsa.pub"
    key.parent.mkdir(parents=True)
    key.write_bytes(b"persistent public key")
elif args[0] in {"start", "image"}:
    pass
elif args[0] == "compose":
    if args[-2:] == ["config", "--images"]:
        print("nginx:fixture")
    elif "sha256sum" in args:
        print(hashlib.sha256(b"persistent public key").hexdigest() + "  /data/config/spacetime/id_ecdsa.pub")
    elif "publish" in args and failure == "publish":
        sys.exit(13)
    elif args[1:] == ["up", "-d", "--no-deps", "db"] and failure == "start":
        # Fail just the replacement. A rollback uses the previous runtime config.
        if (root / "compose.yaml").read_text() == "candidate config":
            sys.exit(14)
else:
    raise RuntimeError("Unexpected Docker arguments: " + repr(args))
"""


class DeploymentRecoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.commands = self.root / "bin"
        self.commands.mkdir()
        for name in ["docker", "curl", "ss", "ufw", "openssl"]:
            path = self.commands / name
            path.write_text(COMMAND_FIXTURE)
            path.chmod(0o755)
        self.candidate = self.root / "incoming/test-release"
        self.candidate.mkdir(parents=True)
        for name in [
            "Dockerfile",
            "compose.yaml",
            ".dockerignore",
            "nginx.conf",
            ".env",
            ".certificate",
            "mt2_server.wasm",
        ]:
            (self.root / name).write_text("previous config")
            (self.candidate / name).write_text("candidate config")
        (self.candidate / "reload-certificate.sh").write_text("fixture hook")
        (self.candidate / "web").mkdir()
        (self.candidate / "web/build-manifest.json").write_text('{"release":"candidate"}')
        (self.root / "web/releases/previous").mkdir(parents=True)
        (self.root / "web/current").symlink_to("releases/previous")
        certificates = self.root / "certificates/test-cert"
        certificates.mkdir(parents=True)
        for name in ["fullchain.pem", "privkey.pem"]:
            (certificates / name).write_text("fixture only")
        script = (deploy.ROOT / "deploy/apply.sh").read_text()
        script = script.replace("game_root=/opt/metin2-godotime", f"game_root={self.root}")
        script = script.replace(
            "hook=/etc/letsencrypt/renewal-hooks/deploy/metin2-godotime",
            f"hook={self.root}/hooks/game",
        )
        script = script.replace("/etc/letsencrypt/live/", str(self.root / "certificates") + "/")
        self.script = self.root / "apply.sh"
        self.script.write_text(script)

    def execute(self, failure):
        result = subprocess.run(
            [
                "bash",
                str(self.script),
                "test-release",
                "test-db",
                "example.test",
                "8443",
                "test-cert",
            ],
            env={
                **os.environ,
                "PATH": str(self.commands) + ":" + os.environ["PATH"],
                "DEPLOY_TEST_ROOT": str(self.root),
                "DEPLOY_TEST_FAILURE": failure,
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        commands = [
            json.loads(line) for line in (self.root / "commands.jsonl").read_text().splitlines()
        ]
        status = json.loads((self.root / "deployment-status.json").read_text())
        return result, commands, status

    def test_invalid_nginx_does_not_stop_database_or_change_runtime(self):
        result, commands, status = self.execute("nginx")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(status["phase"], "failed:validating")
        self.assertFalse(any(command[:2] == ["docker", "stop"] for command in commands))
        self.assertEqual((self.root / "compose.yaml").read_text(), "previous config")
        self.assertEqual(os.readlink(self.root / "web/current"), "releases/previous")

    def test_failed_cold_backup_restarts_previous_container(self):
        result, commands, status = self.execute("backup")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(status["phase"], "failed:backing-up")
        self.assertIn(["docker", "stop", "previous-db"], commands)
        self.assertIn(["docker", "start", "previous-db"], commands)
        self.assertEqual((self.root / "compose.yaml").read_text(), "previous config")
        self.assertFalse(any("publish" in command for command in commands))

    def test_failed_replacement_restores_old_image_and_runtime_without_restoring_data(self):
        result, commands, status = self.execute("start")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(status["phase"], "failed:starting-database")
        self.assertEqual((self.root / "compose.yaml").read_text(), "previous config")
        self.assertIn(
            ["docker", "image", "tag", "sha256:previous-image", "metin2-godotime-db"], commands
        )
        self.assertEqual(
            sum(
                command == ["docker", "compose", "up", "-d", "--no-deps", "db"]
                for command in commands
            ),
            2,
        )
        self.assertFalse(any("publish" in command for command in commands))

    def test_rejected_publication_keeps_old_web_and_never_restores_database(self):
        result, commands, status = self.execute("publish")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(status["phase"], "failed:publishing")
        self.assertEqual(os.readlink(self.root / "web/current"), "releases/previous")
        self.assertFalse(any(command[:3] == ["docker", "image", "tag"] for command in commands))
        publications = [command for command in commands if "publish" in command]
        self.assertEqual(len(publications), 1)
        self.assertIn("--delete-data=never", publications[0])

    def test_success_activates_release_after_publication_and_keeps_backup(self):
        result, commands, status = self.execute("")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(status["phase"], "ready")
        self.assertEqual(os.readlink(self.root / "web/current"), "releases/test-release")
        self.assertTrue(
            (self.root / "backups/test-release/world/config/spacetime/id_ecdsa.pub").is_file()
        )
        publish_at = next(i for i, command in enumerate(commands) if "publish" in command)
        web_at = next(i for i, command in enumerate(commands) if "--force-recreate" in command)
        self.assertLess(publish_at, web_at)
        self.assertTrue((self.root / "hooks/game").is_file())


if __name__ == "__main__":
    unittest.main()
