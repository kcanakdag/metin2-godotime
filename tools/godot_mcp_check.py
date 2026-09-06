"""Exercise the real Godot MCP server while no other process owns its editor port.

python3 tools/godot_mcp_check.py --smoke
python3 tools/godot_mcp_check.py --smoke --preview
python3 tools/godot_mcp_check.py get_editor_screenshot
"""

import argparse
import base64
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".local/mcp"
KEY_F3 = 4_194_334


class MCPClient:
    def __init__(self, port=6505, request_timeout=35):
        self.port = port
        self.request_timeout = request_timeout
        self.process = None
        self.log = None
        self.reader = None
        self.messages = queue.Queue()
        self.sequence = 0

    def __enter__(self):
        node = shutil.which("node")
        server = ROOT / "tools/godot-mcp-server/build/index.js"
        if node is None or not server.is_file():
            raise RuntimeError("Node.js or built MCP server missing. Run `make mcp-build` first.")
        # Probe the exact local address without connecting to or terminating an existing server.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if os.name == "nt":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", self.port))
            except OSError as error:
                raise RuntimeError(
                    f"Cannot bind MCP port {self.port}: {error}. If Codex already owns it, "
                    "use the connected godot tools; do not run this standalone helper concurrently."
                ) from error
        OUTPUT.mkdir(parents=True, exist_ok=True)
        self.log = (OUTPUT / "server.log").open("w")
        try:
            self.process = subprocess.Popen(
                [node, str(server)],
                cwd=ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.log,
                env={**os.environ, "GODOT_MCP_PORT": str(self.port)},
            )
            self.reader = threading.Thread(target=self._read_stdout, daemon=True)
            self.reader.start()
            self.request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "mt2-mcp-check", "version": "2.0"},
                },
            )
            self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            return self
        except BaseException:
            self.close()
            raise

    def _read_stdout(self):
        try:
            for line in self.process.stdout:
                self.messages.put(line)
        finally:
            self.messages.put(None)

    def send(self, message):
        if self.process.poll() is not None:
            raise RuntimeError("MCP server exited; see .local/mcp/server.log.")
        try:
            self.process.stdin.write(json.dumps(message).encode() + b"\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise RuntimeError("MCP server closed stdin; see .local/mcp/server.log.") from error

    def request(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self.request_timeout
        while time.monotonic() < deadline:
            try:
                line = self.messages.get(timeout=max(0.001, deadline - time.monotonic()))
            except queue.Empty:
                break
            if line is None:
                raise RuntimeError("MCP server exited; see .local/mcp/server.log.")
            try:
                message = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise RuntimeError("MCP server wrote invalid JSON to stdout.") from error
            if not isinstance(message, dict):
                raise RuntimeError("MCP response must be a JSON-RPC object.")
            if message.get("id") != request_id:
                continue  # Notifications and replies to an earlier timed-out request.
            if "error" in message:
                raise RuntimeError(f"{method}: {message['error']}")
            if "result" not in message:
                raise RuntimeError(f"{method}: response omitted result.")
            return message["result"]
        raise TimeoutError(
            f"{method} timed out after {self.request_timeout}s; see .local/mcp/server.log."
        )

    def call(self, name, arguments=None):
        response = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        if not isinstance(response, dict) or not isinstance(response.get("content"), list):
            raise RuntimeError(f"{name}: invalid MCP tool response.")
        result = []
        for index, content in enumerate(response["content"]):
            if content.get("type") == "image":
                suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(
                    content.get("mimeType"), ".bin"
                )
                safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", name)
                path = OUTPUT / f"{safe_name}-{index}{suffix}"
                path.write_bytes(base64.b64decode(content["data"], validate=True))
                result.append({"image": str(path), "mime_type": content.get("mimeType")})
            elif content.get("type") == "text":
                text = content.get("text", "")
                try:
                    result.append(json.loads(text))
                except json.JSONDecodeError:
                    result.append(text)  # MCP text is allowed to be plain text.
            else:
                result.append(content)
        if response.get("isError"):
            raise RuntimeError(f"{name}: {result}")
        return result

    def wait_for_editor(self, timeout=75):
        deadline = time.monotonic() + timeout
        while True:
            try:
                return self.call("get_project_info")
            except RuntimeError as error:
                if "not connected" not in str(error).lower() or time.monotonic() >= deadline:
                    raise
                time.sleep(0.5)

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            if self.reader is not None:
                self.reader.join(timeout=1)
            self.process.stdin.close()
            self.process.stdout.close()
            self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None

    def __exit__(self, *exc):
        self.close()


def one_result(values, description):
    if len(values) != 1:
        raise RuntimeError(f"Expected one {description} result, received {len(values)}.")
    return values[0]


def evaluate_json(client, expression):
    # The patched runtime bridge preserves primitive/array/dictionary values as JSON.
    # Expression cannot resolve arbitrary static class names such as JSON itself.
    return one_result(
        client.call("execute_game_script", {"code": expression}),
        "runtime expression",
    )


def validate_project(project):
    data = one_result(project, "project metadata")
    if not isinstance(data, dict) or not isinstance(data.get("project_path"), str):
        raise RuntimeError("Editor did not provide a valid project path.")
    expected = (ROOT / "client").resolve()
    if Path(data["project_path"]).resolve() != expected:
        raise RuntimeError(
            f"Connected editor belongs to {data['project_path']}; expected {expected}."
        )
    return data


def wait_for_scene(client, expected, timeout=20):
    deadline = time.monotonic() + timeout
    last_error = "scene has not started"
    while time.monotonic() < deadline:
        try:
            actual = evaluate_json(client, "get_tree().current_scene.scene_file_path")
            if actual == expected:
                return client.call("get_game_scene_tree")
            last_error = f"running scene is {actual!r}"
        except RuntimeError as error:
            last_error = str(error)
        time.sleep(0.25)
    raise RuntimeError(f"Could not start {expected}: {last_error}")


def stop_and_verify(client):
    result = client.call("stop_scene")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            client.call("get_game_scene_tree")
        except RuntimeError as error:
            if "game is not running" in str(error).lower():
                return {"request": result, "confirmed_stopped": True}
        time.sleep(0.25)
    raise RuntimeError("Editor did not confirm the game stopped.")


def screenshot(client, label):
    result = client.call("get_game_screenshot")
    images = [entry["image"] for entry in result if isinstance(entry, dict) and "image" in entry]
    if not images:
        raise RuntimeError("Game screenshot tool returned no image.")
    shutil.copy2(images[0], OUTPUT / f"{label}.png")
    return result


def key_press(client, keycode):
    client.call("simulate_key", {"keycode": keycode, "pressed": True})
    client.call("simulate_key", {"keycode": keycode, "pressed": False})


def world_smoke(client, report):
    before = evaluate_json(client, "get_tree().current_scene.dev_snapshot()")
    if not isinstance(before, dict) or not isinstance(before.get("debug_visible"), bool):
        raise RuntimeError("Main dev_snapshot() must expose a boolean debug_visible.")
    report["world_before"] = before
    report["world_screenshot"] = screenshot(client, "world")
    key_press(client, KEY_F3)
    deadline = time.monotonic() + 5
    after = before
    while time.monotonic() < deadline:
        after = evaluate_json(client, "get_tree().current_scene.dev_snapshot()")
        if not isinstance(after, dict) or not isinstance(after.get("debug_visible"), bool):
            raise RuntimeError("World snapshot lost its boolean debug_visible field.")
        if after.get("debug_visible") is not before["debug_visible"]:
            break
        time.sleep(0.1)
    if after.get("debug_visible") is not (not before["debug_visible"]):
        raise RuntimeError("Simulated F3 did not toggle the debug menu.")
    report["world_after_input"] = after
    report["debug_screenshot"] = screenshot(client, "debug")
    key_press(client, KEY_F3)
    print("World snapshot, F3 input, game and debug screenshots: OK", flush=True)


def preview_smoke(client, report):
    report["idle_screenshot"] = screenshot(client, "idle")
    for name in ("wait", "walk", "run", "attack"):
        result = evaluate_json(client, f'get_tree().current_scene.play_animation("{name}")')
        if not isinstance(result, dict) or result.get("animation") != name:
            raise RuntimeError(f"Preview animation {name} unavailable: {result}")
        report[name] = result
    key_press(client, 51)
    time.sleep(0.25)
    current = evaluate_json(client, "get_tree().current_scene.current_clip")
    if current != "run":
        raise RuntimeError(f"Preview Run key selected {current!r}, expected 'run'.")
    report["input_result"] = current
    report["run_screenshot"] = screenshot(client, "run")
    print("Four preview clips and simulated Run key: OK", flush=True)


def smoke(client, project, preview=False):
    scene = "res://scenes/character_preview.tscn" if preview else "res://scenes/main.tscn"
    play = {"mode": "custom", "scene_path": scene} if preview else {"mode": "main"}
    report = {
        "status": "running",
        "mode": "preview" if preview else "world",
        "project": project,
        "tool_count": len(client.request("tools/list", {})["tools"]),
    }
    try:
        report["initial_stop"] = stop_and_verify(client)
        report["editor_tree"] = client.call("get_scene_tree")
        report["editor_screenshot"] = client.call("get_editor_screenshot")
        if not any(
            isinstance(entry, dict) and "image" in entry for entry in report["editor_screenshot"]
        ):
            raise RuntimeError("Editor screenshot tool returned no image.")
        report["play"] = client.call("play_scene", play)
        report["runtime_tree"] = wait_for_scene(client, scene)
        print("Editor/project validation, both scene trees, and scene start: OK", flush=True)
        if preview:
            preview_smoke(client, report)
        else:
            world_smoke(client, report)
        report["stop"] = stop_and_verify(client)
        report["restart"] = client.call("play_scene", play)
        report["restarted_tree"] = wait_for_scene(client, scene)
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        # Leave the current scene visible for diagnosis, but the context closes the Node server.
        raise
    finally:
        path = OUTPUT / ("preview-report.json" if preview else "report.json")
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Report: {path}", flush=True)
    print("Stop/restart verified; client left running for inspection.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", nargs="?", default="get_project_info")
    parser.add_argument("--args", default="{}", help="JSON object of tool arguments")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument(
        "--preview", action="store_true", help="Use the character preview in smoke mode"
    )
    parser.add_argument("--port", type=int, default=6505)
    options = parser.parse_args()
    if options.preview and not options.smoke:
        parser.error("--preview requires --smoke")
    if not 1 <= options.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        arguments = json.loads(options.args)
    except json.JSONDecodeError as error:
        parser.error(f"--args is not valid JSON: {error}")
    if not isinstance(arguments, dict):
        parser.error("--args must be a JSON object")
    with MCPClient(port=options.port) as client:
        project = client.wait_for_editor()
        validate_project(project)
        if options.smoke:
            smoke(client, project, options.preview)
        else:
            print(json.dumps(client.call(options.tool, arguments), indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Godot MCP check failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except KeyboardInterrupt:
        print("Godot MCP check interrupted; helper server stopped.", file=sys.stderr)
        raise SystemExit(130) from None
