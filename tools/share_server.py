#!/usr/bin/env python3
"""Run an optional temporary Cloudflare playtest link for this game's local server."""

import argparse
import fcntl
import hashlib
import json
import os
import platform
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local/playtest"
STATE = LOCAL / "session.json"
VERSION = "2026.8.3"
DIGEST = "f29324fe934d1e100617484c78deef803c4dc2cd351d645bbde42e96b4fccc5e"
BINARY = ROOT / ".cache/cloudflared" / VERSION / "cloudflared"
DOWNLOAD = (
    f"https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-linux-amd64"
)


def get_json(url, timeout=5, accept="application/json"):
    request = urllib.request.Request(
        url, headers={"User-Agent": "mt2spacetime-playtest", "Accept": accept}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def public_dns_ready(url):
    # A lookup before Quick Tunnel DNS publication can poison a router's negative
    # cache for 30 minutes. Wait for public DNS before asking the system resolver.
    query = urlencode({"name": urlsplit(url).hostname, "type": "A"})
    answer = get_json(
        f"https://cloudflare-dns.com/dns-query?{query}", accept="application/dns-json"
    )
    return answer.get("Status") == 0 and any(
        record.get("type") == 1 for record in answer.get("Answer", [])
    )


def write_state(value):
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(STATE)


def process_start(pid):
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
        return text[text.rfind(")") + 2 :].split()[19]
    except (OSError, IndexError):
        return None


def active_state(*, allow_starting=False):
    if not STATE.is_file():
        raise RuntimeError("No shared playtest is running. Run make share-start first.")
    value = json.loads(STATE.read_text())
    live = value.get("owner_start") and process_start(value.get("owner_pid", 0)) == value.get(
        "owner_start"
    )
    owner = Path(f"/proc/{value.get('owner_pid', 0)}")
    try:
        arguments = (owner / "cmdline").read_bytes().decode().split("\0")
        owner_cwd = (owner / "cwd").resolve()
        correct_command = (
            len(arguments) >= 3
            and (owner / "exe").resolve() == Path(sys.executable).resolve()
            and (owner_cwd / arguments[1]).resolve() == Path(__file__).resolve()
            and arguments[2] == "start"
        )
    except OSError:
        correct_command = False
    statuses = {"ready", "starting"} if allow_starting else {"ready"}
    if value.get("status") not in statuses or not live or not correct_command:
        raise RuntimeError("The recorded playtest is no longer running. Run make share-start.")
    return value


def install():
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise RuntimeError(
            "This host helper currently supports Linux x86_64; Windows players need no helper."
        )
    if BINARY.is_file() and hashlib.sha256(BINARY.read_bytes()).hexdigest() == DIGEST:
        print(f"cloudflared {VERSION} already installed and verified: {BINARY}")
        return
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    temporary = BINARY.with_suffix(".download")
    request = urllib.request.Request(DOWNLOAD, headers={"User-Agent": "mt2spacetime-playtest"})
    print(f"Downloading pinned cloudflared {VERSION}…", flush=True)
    try:
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            temporary.open("wb") as output,
        ):
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        actual = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if actual != DIGEST:
            raise RuntimeError(f"cloudflared checksum mismatch: {actual}")
        temporary.chmod(0o755)
        temporary.replace(BINARY)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Installed verified host tool: {BINARY}")


def start(options):
    if not BINARY.is_file() or hashlib.sha256(BINARY.read_bytes()).hexdigest() != DIGEST:
        raise RuntimeError("Pinned cloudflared missing or changed. Run make share-setup first.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", options.database):
        raise RuntimeError("Use a lowercase database name containing letters, digits, _ or -.")
    upstream = f"http://127.0.0.1:{options.server_port}"
    get_json(f"{upstream}/v1/database/{options.database}")
    LOCAL.mkdir(parents=True, exist_ok=True)
    lock = (LOCAL / "session.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock.close()
        raise RuntimeError(
            "A playtest launcher already owns this session. Use make share-status."
        ) from error
    config = LOCAL / "empty-config.yml"
    config.write_text("{}\n")
    logs = []
    children = []
    value = {
        "status": "starting",
        "database": options.database,
        "owner_pid": os.getpid(),
        "owner_start": process_start(os.getpid()),
        "upstream": upstream,
        "gateway_port": options.gateway_port,
        "cloudflared_version": VERSION,
    }
    write_state(value)

    def spawn(command, filename):
        log = (LOCAL / filename).open("w")
        logs.append(log)
        child = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT
        )
        children.append(child)
        return child

    def interrupted(_signal, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        ready_path = LOCAL / f"gateway-{os.getpid()}-{time.time_ns()}.json"
        gateway = spawn(
            [
                sys.executable,
                str(ROOT / "tools/playtest_gateway.py"),
                "--database",
                options.database,
                "--upstream",
                upstream,
                "--listen-port",
                str(options.gateway_port),
                "--ready-file",
                str(ready_path),
            ],
            "gateway.log",
        )
        gateway_url = f"http://127.0.0.1:{options.gateway_port}"
        deadline = time.monotonic() + 10
        while True:
            if gateway.poll() is not None:
                raise RuntimeError("Game gateway exited; inspect .local/playtest/gateway.log.")
            try:
                if not ready_path.is_file():
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Game gateway did not publish its readiness record.")
                    time.sleep(0.1)
                    continue
                ready = json.loads(ready_path.read_text())
                if ready.get("pid") != gateway.pid or ready.get("database") != options.database:
                    raise RuntimeError("Game gateway readiness belongs to another process.")
                health = get_json(gateway_url + "/health")
                if health.get("database") != options.database:
                    raise RuntimeError("Gateway port belongs to a different game.")
                break
            except urllib.error.URLError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Game gateway did not become ready.") from None
                time.sleep(0.1)
        tunnel = spawn(
            [
                str(BINARY),
                "tunnel",
                "--config",
                str(config),
                "--no-autoupdate",
                "--loglevel",
                "info",
                "--transport-loglevel",
                "info",
                "--url",
                gateway_url,
                "--protocol",
                "http2",
                "--edge-ip-version",
                "4",
                "--metrics",
                f"127.0.0.1:{options.metrics_port}",
            ],
            "cloudflared.log",
        )
        value.update({"gateway_pid": gateway.pid, "tunnel_pid": tunnel.pid})
        write_state(value)
        print("Opening temporary HTTPS playtest link…", flush=True)
        deadline = time.monotonic() + 90
        url = ""
        health_error = "No public URL received"
        dns_ready = False
        while time.monotonic() < deadline:
            if gateway.poll() is not None or tunnel.poll() is not None:
                raise RuntimeError("A playtest process exited; inspect .local/playtest/*.log.")
            log_text = (LOCAL / "cloudflared.log").read_text(errors="replace")[-65536:]
            matches = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", log_text)
            if matches:
                url = matches[-1]
                try:
                    if not dns_ready:
                        dns_ready = public_dns_ready(url)
                    if not dns_ready:
                        health_error = "Waiting for public DNS publication"
                        time.sleep(0.5)
                        continue
                    if get_json(url + "/health").get("database") == options.database:
                        break
                except (OSError, ValueError) as error:
                    health_error = str(error)
            time.sleep(0.5)
        else:
            raise RuntimeError(
                f"Public endpoint {url or '(not assigned)'} did not become healthy: {health_error}. "
                "Inspect .local/playtest/cloudflared.log."
            )
        value.update({"status": "ready", "server_url": url})
        write_state(value)
        print(f"Server: {url}\nDatabase: {options.database}", flush=True)
        print("Run make export-shared in another terminal to package this address.", flush=True)
        print(
            "Keep this terminal and the database running. Ctrl+C closes only the public link.",
            flush=True,
        )
        while gateway.poll() is None and tunnel.poll() is None:
            time.sleep(0.5)
        raise RuntimeError("A playtest process stopped; inspect .local/playtest/*.log.")
    except KeyboardInterrupt:
        print("Closing playtest link; local database remains running.", flush=True)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                try:
                    child.terminate()
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        child.kill()
                    except ProcessLookupError:
                        pass
                    child.wait(timeout=5)
                except ProcessLookupError:
                    pass
        for log in logs:
            log.close()
        value["status"] = "stopped"
        write_state(value)
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("install", help="Download the pinned host binary into .cache")
    start_parser = sub.add_parser("start", help="Run a temporary public playtest until Ctrl+C")
    start_parser.add_argument("--database", default="mt2-dev-world")
    start_parser.add_argument("--server-port", type=int, default=3210)
    start_parser.add_argument("--gateway-port", type=int, default=3211)
    start_parser.add_argument("--metrics-port", type=int, default=3212)
    sub.add_parser("status", help="Verify the recorded launcher and public health route")
    sub.add_parser("url", help="Print the active public address")
    sub.add_parser("stop", help="Ask only this verified launcher process to close its link")
    export_parser = sub.add_parser(
        "export", help="Export the Windows client with this active address"
    )
    export_parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    export_parser.add_argument("--wine-smoke", action="store_true")
    options = parser.parse_args()
    if options.action == "install":
        install()
        return
    if options.action == "start":
        start(options)
        return
    value = active_state(allow_starting=options.action == "stop")
    if options.action == "stop":
        os.kill(value["owner_pid"], signal.SIGTERM)
        print("Requested playtest shutdown; local SpacetimeDB is unchanged.")
        return
    health = get_json(value["server_url"] + "/health")
    if health.get("database") != value["database"]:
        raise RuntimeError("Public health route returned a different database.")
    if options.action == "url":
        print(value["server_url"])
    elif options.action == "status":
        print(json.dumps({**value, "public_health": health}, indent=2))
    else:
        command = [
            sys.executable,
            str(ROOT / "tools/export_client.py"),
            "--godot",
            options.godot,
            "--server",
            value["server_url"],
            "--database",
            value["database"],
        ]
        if options.wine_smoke:
            command.append("--wine-smoke")
        subprocess.run(command, check=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
