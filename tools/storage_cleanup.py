#!/usr/bin/env python3
"""Report and reclaim local SpacetimeDB replica storage.

The standalone development server keeps one directory per database under
``<data-dir>/replicas/``.  Publishing a fresh database for every QA run grows
that directory until the disk fills, so this tool answers two questions from one
shared snapshot: which databases still deserve to exist, and which replica
directories can be removed.

The identity mapping is authoritative instead of heuristic:

* ``spacetime list`` reports the name and identity of every database owned by
  the configured CLI identity.
* the server log records ``launching module db=<identity> replica=<dir>`` and
  the ``db.lock`` path of a pending launch, which maps identities to replica
  directories.  A directory reused by a later database keeps its latest owner.

Reclamation runs in two phases because a listening server owns its files::

    python3 tools/storage_cleanup.py report
    python3 tools/storage_cleanup.py entries --apply
    # stop the standalone server
    python3 tools/storage_cleanup.py files --manifest MANIFEST --apply
    # start the standalone server again

``files --restart-server`` performs the stop and start itself: it reads
``<data-dir>/spacetime.pid``, refuses to signal a process whose command line does
not mention that data directory, removes the recorded directories, and starts
the recorded command line again with the same working directory and log.

``entries`` drops obsolete database rows through the SpacetimeDB CLI for
databases the CLI identity owns, and records exactly which replica directories
those databases used.  ``files`` removes only directories named by such a
manifest, so a directory that belongs to another identity is never touched even
when its database name is unknown to this tool.  Both phases default to a dry
run.

A directory whose database entry is gone but whose files remain is probed with
``spacetime describe``; the server answers ``404`` only when the identity is not
attached to any database, so those orphans join the removal manifest instead of
being guessed at from file names.

Retention keeps any database active within ``--keep-days`` and any database
whose name matches a ``--keep`` glob; ``mt2-p1`` and ``mt2-p1-final`` are pinned
by default.  Pass ``--keep '*'`` to retain every owned database.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / ".local/p1/server"
DEFAULT_CONFIG_PATH = ROOT / ".local/p1/cli.toml"
DEFAULT_SERVER = "http://127.0.0.1:13223"
DEFAULT_KEEP_DAYS = 2.0
DEFAULT_BUDGET_GB = 8.0
DEFAULT_KEEP = ("mt2-p1", "mt2-p1-final")
MANIFEST_VERSION = 1

IDENTITY_PATTERN = re.compile(r"[0-9a-f]{64}")
REPLICA_DIR_PATTERN = re.compile(r"[0-9]+")
LAUNCH_PATTERN = re.compile(r"launching module db=([0-9a-f]{64}) replica=(\d+)")
LOCK_PATTERN = re.compile(r"Acquired lock on .*?/replicas/(\d+)/db\.lock")


def directory_bytes(path: Path) -> int:
    """Return the total size of every regular file below ``path``."""
    total = 0
    for root, _directories, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total


def read_replica_identities(data_dir: Path) -> dict[str, str]:
    """Map replica directory names to database identities using the server log.

    A launch that opens a new replica logs ``replica=0`` and the real directory
    on the ``db.lock`` line that follows, so the pending identity is resolved by
    the next acquired lock.  Later launches overwrite earlier ones because a
    directory number can be reused by a different database.
    """
    log_path = data_dir / "logs/spacetime-standalone.log"
    mapping: dict[str, str] = {}
    if not log_path.is_file():
        return mapping
    pending: str | None = None
    with log_path.open("r", errors="replace") as stream:
        for line in stream:
            launch = LAUNCH_PATTERN.search(line)
            if launch:
                identity, replica = launch.group(1), launch.group(2)
                if replica == "0":
                    pending = identity
                else:
                    mapping[replica] = identity
                    pending = None
                continue
            lock = LOCK_PATTERN.search(line)
            if lock and pending is not None:
                mapping[lock.group(1)] = pending
                pending = None
    return mapping


def run_command(command: list[str]) -> tuple[int, str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return completed.returncode, completed.stdout + completed.stderr


def cli_command(spacetime: str, config_path: Path, rest: list[str]) -> list[str]:
    command = [spacetime]
    if config_path.is_file():
        command += ["--config-path", str(config_path)]
    return command + rest


def parse_owned_names(output: str) -> dict[str, str]:
    """Parse ``spacetime list`` output into a database-name to identity map."""
    owned: dict[str, str] = {}
    for line in output.splitlines():
        if "|" not in line:
            continue
        names, _, identity = line.partition("|")
        identity = identity.strip()
        if not IDENTITY_PATTERN.fullmatch(identity):
            continue
        for name in (part.strip() for part in names.split(",")):
            if name.startswith("mt2-"):
                owned[name] = identity
    return owned


def owned_names(
    spacetime: str, server: str, config_path: Path, runner=run_command
) -> dict[str, str]:
    """Return the databases the stored CLI identity owns on the local server."""
    command = cli_command(spacetime, config_path, ["list", "--server", server])
    code, output = runner(command)
    if code != 0:
        raise RuntimeError(f"`{spacetime} list` failed with exit code {code}: {output.strip()}")
    return parse_owned_names(output)


def probe_database(
    spacetime: str, server: str, config_path: Path, identity: str, runner=run_command
) -> bool | None:
    """Ask the server whether ``identity`` is still attached to a database.

    ``spacetime describe`` resolves the identity without requiring ownership, so
    ``True`` means the database exists for somebody, ``False`` means the control
    database has no such entry any more, and ``None`` means the probe itself was
    inconclusive and the directory must be left alone.
    """
    command = cli_command(
        spacetime, config_path, ["describe", "--json", "--server", server, identity]
    )
    code, output = runner(command)
    if code == 0:
        return True
    if "No such database" in output or "404 Not Found" in output:
        return False
    return None


def build_snapshot(data_dir: Path, owned: dict[str, str] | None, probe=None) -> dict:
    """Describe every replica directory with its names, size and age."""
    replicas = data_dir / "replicas"
    identities = read_replica_identities(data_dir)
    names_by_identity: dict[str, list[str]] = {}
    for name, identity in (owned or {}).items():
        names_by_identity.setdefault(identity, []).append(name)

    now = time.time()
    rows = []
    if replicas.is_dir():
        for entry in sorted(replicas.iterdir(), key=lambda path: path.name):
            if not entry.is_dir():
                continue
            identity = identities.get(entry.name)
            names = sorted(names_by_identity.get(identity or "", []))
            # Only directories without an owned database name need the server
            # probe; everything else is already classified by name.
            attached = None
            if probe is not None and identity and not names:
                attached = probe(identity)
            modified = entry.stat().st_mtime
            rows.append(
                {
                    "dir": entry.name,
                    "path": str(entry),
                    "bytes": directory_bytes(entry),
                    "modified": datetime.fromtimestamp(modified, UTC).isoformat(),
                    "age_days": round((now - modified) / 86400.0, 2),
                    "identity": identity,
                    "names": names,
                    "attached": attached,
                }
            )
    return {
        "data_dir": str(data_dir),
        "generated": datetime.now(UTC).isoformat(),
        "names_available": owned is not None,
        "replicas": rows,
        "total_bytes": sum(row["bytes"] for row in rows),
    }


def retention_reason(row: dict, keep_days: float, keep_patterns: list[str]) -> str | None:
    """Return why a replica must be retained, or ``None`` when it is obsolete."""
    if row["age_days"] <= keep_days:
        return f"active within {keep_days:g} days"
    for name in row["names"]:
        if any(fnmatch.fnmatch(name, pattern) for pattern in keep_patterns):
            return f"matches keep pattern for {name}"
    return None


def classify(snapshot: dict, keep_days: float, keep_patterns: list[str]) -> list[dict]:
    """Annotate every replica row with retention state and reclaim readiness."""
    for row in snapshot["replicas"]:
        row["retained"] = retention_reason(row, keep_days, keep_patterns)
        # `entries` can only drop names this CLI identity owns; directories of
        # other identities are reported and then left alone.
        row["obsolete_named"] = row["retained"] is None and bool(row["names"])
        row["unattached"] = row["retained"] is None and not row["names"]
        row["unknown_identity"] = row["identity"] is None
        row["orphan"] = row["unattached"] and row.get("attached") is False
    return snapshot["replicas"]


def megabytes(value: int | float) -> str:
    return f"{value / 1e6:.1f} MB" if value < 1e9 else f"{value / 1e9:.2f} GB"


def print_report(snapshot: dict, rows: list[dict], budget_gb: float) -> None:
    total = snapshot["total_bytes"]
    obsolete = [row for row in rows if row["obsolete_named"]]
    retained = [row for row in rows if row["retained"]]
    unattached = [row for row in rows if row["unattached"]]
    orphans = [row for row in unattached if row["orphan"]]
    print(f"data dir : {snapshot['data_dir']}")
    print(f"replicas : {len(rows)} directories, {megabytes(total)} (budget {budget_gb:g} GB)")
    print(f"retained : {len(retained)} directories, {megabytes(sum(r['bytes'] for r in retained))}")
    print(
        f"obsolete : {len(obsolete)} named databases, {megabytes(sum(r['bytes'] for r in obsolete))}"
    )
    if not snapshot["names_available"]:
        print("names    : unavailable (offline review); database owners were not queried")
    print(
        "detached : "
        f"{len(unattached)} directories without an owned name, "
        f"{megabytes(sum(r['bytes'] for r in unattached))} "
        "(other identities; removed only through an `entries` manifest)"
    )
    print(
        f"orphans  : {len(orphans)} directories, {megabytes(sum(r['bytes'] for r in orphans))} "
        "(database entry gone, files still on disk)"
    )
    if total > budget_gb * 1e9:
        print(f"WARNING  : replica storage exceeds the {budget_gb:g} GB budget")
    print()
    print(f"{'directory':>10}  {'size':>11}  {'age d':>6}  database / state")
    for row in sorted(rows, key=lambda item: item["bytes"], reverse=True):
        if row["retained"]:
            state = "keep: " + row["retained"]
        elif row["obsolete_named"]:
            state = "entry removable (then files)"
        elif row["orphan"]:
            state = "orphan: entry already gone"
        elif row["orphan"] is False and row["unattached"]:
            state = "other identity, still attached"
        elif row["unknown_identity"]:
            state = "unknown identity, never touched"
        else:
            state = "other identity, probe inconclusive"
        label = ", ".join(row["names"]) or "(unnamed for this identity)"
        print(
            f"{row['dir']:>10}  {megabytes(row['bytes']):>11}  {row['age_days']:>6.2f}  {label[:58]} [{state}]"
        )
    if obsolete or orphans:
        print()
        print("next: `entries --apply` drops the removable entries and writes a removal manifest")
        print("      that includes the orphans; then stop the server and run")
        print("      `files --manifest MANIFEST --apply`.")


def plan_entries(rows: list[dict], owned: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Split obsolete owned databases into the deletable and the unowned."""
    planned: list[dict] = []
    unowned: list[dict] = []
    for row in rows:
        if not row["obsolete_named"]:
            continue
        for name in row["names"]:
            record = {
                "name": name,
                "identity": owned.get(name),
                "dir": row["dir"],
                "bytes": row["bytes"],
            }
            (planned if record["identity"] else unowned).append(record)
    return planned, unowned


def apply_entry_deletions(
    planned: list[dict],
    spacetime: str,
    server: str,
    config_path: Path,
    apply: bool,
    runner=run_command,
) -> dict:
    """Delete planned database entries, reporting each outcome."""
    deleted, failed = [], []
    for record in planned:
        if not apply:
            deleted.append(record)
            continue
        command = cli_command(
            spacetime, config_path, ["delete", "--server", server, "-y", record["name"]]
        )
        code, output = runner(command)
        if code == 0:
            deleted.append(record)
        else:
            failed.append(record | {"error": output.strip()})
    return {"deleted": deleted, "failed": failed, "applied": apply}


def default_manifest_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / ".local/maintenance" / f"storage-cleanup-{stamp}" / "detached.json"


def write_json(path: Path | None, payload: dict, quiet: bool = False) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n")
    if not quiet:
        print(f"wrote {path}")


def build_manifest(
    snapshot: dict, server: str, deleted: list[dict], orphans: list[dict] | None = None
) -> dict:
    entries = [
        {
            "name": record["name"],
            "identity": record["identity"],
            "dir": record["dir"],
            "bytes": record["bytes"],
            "source": "detached-entry",
        }
        for record in deleted
    ]
    for row in orphans or []:
        entries.append(
            {
                "name": None,
                "identity": row["identity"],
                "dir": row["dir"],
                "bytes": row["bytes"],
                "source": "orphan-probe",
            }
        )
    return {
        "version": MANIFEST_VERSION,
        "generated": datetime.now(UTC).isoformat(),
        "data_dir": snapshot["data_dir"],
        "server": server,
        "entries": entries,
        "planned_bytes": sum(record["bytes"] for record in entries if record["dir"]),
    }


def load_manifest(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f"manifest not found: {path}")
    try:
        manifest = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise RuntimeError(f"manifest is not valid JSON: {path}: {error}") from error
    if manifest.get("version") != MANIFEST_VERSION:
        raise RuntimeError(f"unsupported manifest version in {path}: {manifest.get('version')!r}")
    return manifest


def server_address(server: str) -> tuple[str, int]:
    parsed = urlparse(server)
    return parsed.hostname or "127.0.0.1", parsed.port or 80


def server_listening(server: str) -> bool:
    host, port = server_address(server)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(1.0)
            return probe.connect_ex((host, port)) == 0
    except OSError:
        return False


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_pid_file(data_dir: Path) -> int | None:
    pid_file = data_dir / "spacetime.pid"
    if not pid_file.is_file():
        return None
    try:
        return int(pid_file.read_text().strip())
    except ValueError:
        return None


def log_target_for(pid: int, data_dir: Path) -> Path:
    """Return where a restarted server should append its console output."""
    fallback = data_dir.parent / "server.log"
    try:
        target = os.readlink(f"/proc/{pid}/fd/1")
    except OSError:
        return fallback
    if target.startswith("/") and not target.startswith("/dev/"):
        return Path(target)
    return fallback


def stop_standalone_server(data_dir: Path, server: str, timeout: float = 30.0) -> dict | None:
    """Stop the standalone server this data directory belongs to, if any.

    The process is only signalled when its command line mentions the data
    directory, so a stale pid file can never take down an unrelated service.
    Returns the restart recipe, or ``None`` when no running server was found.
    """
    pid = read_pid_file(data_dir)
    if pid is None or not process_alive(pid):
        return None
    try:
        raw_argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError as error:
        raise RuntimeError(f"cannot read the command line of server pid {pid}: {error}") from error
    argv = [part.decode(errors="replace") for part in raw_argv if part]
    if not any(str(data_dir) in part for part in argv):
        raise RuntimeError(f"pid {pid} does not serve {data_dir}; refusing to stop it")
    try:
        cwd = os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        cwd = str(ROOT)
    log_target = log_target_for(pid, data_dir)
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + timeout
    while process_alive(pid):
        if time.time() > deadline:
            raise RuntimeError(f"server pid {pid} did not stop within {timeout:g}s")
        time.sleep(0.25)
    while server_listening(server) and time.time() < deadline:
        time.sleep(0.25)
    return {"pid": pid, "argv": argv, "cwd": cwd, "log": str(log_target)}


def start_standalone_server(recipe: dict, server: str, timeout: float = 60.0) -> int:
    """Start a stopped server again with the recorded command line."""
    log_path = Path(recipe["log"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as stream:
        process = subprocess.Popen(
            recipe["argv"],
            cwd=recipe["cwd"],
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server_listening(server):
            return process.pid
        if process.poll() is not None:
            raise RuntimeError(
                f"server exited with code {process.returncode}; start it again with: {' '.join(recipe['argv'])}"
            )
        time.sleep(0.5)
    raise RuntimeError(f"server pid {process.pid} did not start listening within {timeout:g}s")


def remove_manifest_files(
    manifest: dict,
    data_dir: Path,
    live_identities: set[str] | None,
    apply: bool,
) -> dict:
    """Remove the replica directories a detached-entry manifest recorded.

    Every candidate has to survive three guards: the recorded directory must be
    a numbered child of this data directory, the newest server-log owner of that
    directory must still match the recorded identity, and that identity must no
    longer be attached to a live database.
    """
    replicas = (data_dir / "replicas").resolve()
    identities = read_replica_identities(data_dir)
    removed, skipped = [], []
    freed = 0
    for record in manifest.get("entries", []):
        directory = record.get("dir")
        if not directory:
            skipped.append(record | {"reason": "no replica directory recorded"})
            continue
        if not REPLICA_DIR_PATTERN.fullmatch(str(directory)):
            skipped.append(record | {"reason": f"not a numeric replica directory: {directory!r}"})
            continue
        path = (replicas / str(directory)).resolve()
        if path.parent != replicas:
            skipped.append(record | {"reason": f"outside the replica directory: {path}"})
            continue
        recorded_identity = record.get("identity")
        current_identity = identities.get(str(directory))
        if current_identity is None:
            skipped.append(record | {"reason": "no server-log owner recorded for this directory"})
            continue
        if current_identity != recorded_identity:
            skipped.append(
                record
                | {
                    "reason": f"directory now belongs to {current_identity}, not {recorded_identity}"
                }
            )
            continue
        if live_identities is not None and recorded_identity in live_identities:
            skipped.append(record | {"reason": "identity is still attached to a database entry"})
            continue
        if not path.is_dir():
            skipped.append(record | {"reason": "directory is already gone"})
            continue
        size = directory_bytes(path)
        if apply:
            shutil.rmtree(path)
        removed.append(record | {"path": str(path), "bytes": size})
        freed += size
    return {"removed": removed, "skipped": skipped, "freed": freed, "applied": apply}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("action", choices=("report", "entries", "files"))
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--spacetime", default=os.environ.get("SPACETIME", "spacetime"))
    parser.add_argument("--keep-days", type=float, default=DEFAULT_KEEP_DAYS)
    parser.add_argument("--keep", action="append", default=[], help="database name glob to retain")
    parser.add_argument("--budget-gb", type=float, default=DEFAULT_BUDGET_GB)
    parser.add_argument(
        "--manifest", type=Path, default=None, help="`files`: manifest written by `entries --apply`"
    )
    parser.add_argument(
        "--manifest-out", type=Path, default=None, help="`entries`: where to write the manifest"
    )
    parser.add_argument(
        "--orphan-manifest",
        type=Path,
        default=None,
        help="`report`: write a removal manifest for orphan directories",
    )
    parser.add_argument(
        "--offline", action="store_true", help="skip the CLI query and report sizes only"
    )
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--apply", action="store_true", help="perform changes instead of a dry run")
    parser.add_argument(
        "--force", action="store_true", help="allow `files` while a server is listening"
    )
    parser.add_argument(
        "--restart-server",
        action="store_true",
        help="`files --apply`: stop the recorded standalone server, remove the files, start it again",
    )
    return parser.parse_args(argv)


def keep_patterns(options: argparse.Namespace) -> list[str]:
    return list(DEFAULT_KEEP) + list(options.keep)


def make_probe(options: argparse.Namespace):
    """Return a probe that asks the configured server whether an identity is live."""

    def probe(identity: str) -> bool | None:
        return probe_database(options.spacetime, options.server, options.config_path, identity)

    return probe


def run_report(options: argparse.Namespace, owned: dict[str, str] | None) -> int:
    probe = None if options.offline else make_probe(options)
    snapshot = build_snapshot(options.data_dir, owned, probe)
    rows = classify(snapshot, options.keep_days, keep_patterns(options))
    print_report(snapshot, rows, options.budget_gb)
    snapshot["budget_gb"] = options.budget_gb
    orphans = [row for row in rows if row["orphan"]]
    if options.orphan_manifest is not None:
        if orphans:
            write_json(
                options.orphan_manifest, build_manifest(snapshot, options.server, [], orphans)
            )
        else:
            print("no orphan directories to record; no manifest written")
    write_json(options.json, snapshot)
    return 0


def run_entries(options: argparse.Namespace, owned: dict[str, str]) -> int:
    snapshot = build_snapshot(options.data_dir, owned, make_probe(options))
    rows = classify(snapshot, options.keep_days, keep_patterns(options))
    planned, unowned = plan_entries(rows, owned)
    orphans = [row for row in rows if row["orphan"]]
    result = apply_entry_deletions(
        planned,
        options.spacetime,
        options.server,
        options.config_path,
        options.apply,
    )
    manifest = build_manifest(snapshot, options.server, result["deleted"], orphans)
    manifest_path = options.manifest_out or (default_manifest_path() if options.apply else None)
    write_json(manifest_path, manifest, quiet=options.json is not None)
    snapshot["entries"] = result | {"manifest": str(manifest_path) if manifest_path else None}
    verb = "deleted" if options.apply else "would delete"
    print(f"{verb} {len(result['deleted'])} database entries")
    print(f"left alone {len(unowned)} obsolete names this identity does not own")
    if orphans:
        print(f"recorded {len(orphans)} already-detached replica directories for removal")
    if result["failed"]:
        print(f"failed {len(result['failed'])} entries", file=sys.stderr)
        for failure in result["failed"]:
            print(f"  {failure['name']}: {failure['error']}", file=sys.stderr)
    if not options.apply:
        print("dry run: pass --apply to delete these entries (keeps the replica files)")
    elif manifest_path is not None:
        print("next: stop the server, then run `files --manifest <manifest> --apply`")
    write_json(options.json, snapshot)
    return 1 if result["failed"] else 0


def run_files(options: argparse.Namespace) -> int:
    if options.manifest is None:
        print("`files` requires --manifest from `entries --apply`", file=sys.stderr)
        return 2
    manifest = load_manifest(options.manifest)
    data_dir = Path(manifest.get("data_dir") or options.data_dir)
    if not data_dir.is_dir():
        print(f"data dir not found: {data_dir}", file=sys.stderr)
        return 1
    live_identities: set[str] | None = None
    if not options.offline:
        try:
            live = owned_names(options.spacetime, options.server, options.config_path)
        except RuntimeError:
            live = None
        if live is not None:
            live_identities = set(live.values())

    recipe: dict | None = None
    if server_listening(options.server):
        if options.restart_server and options.apply:
            recipe = stop_standalone_server(data_dir, options.server)
            if recipe is None:
                print(
                    f"a SpacetimeDB server is listening on {options.server} but {data_dir}/spacetime.pid "
                    "did not identify it; stop it manually or pass --force",
                    file=sys.stderr,
                )
                return 1
            print(f"stopped server pid {recipe['pid']} for the file removal")
        elif not options.apply:
            print(
                f"note: a SpacetimeDB server is listening on {options.server}; pass --restart-server "
                "with --apply to stop it, remove the files and start it again"
            )
        elif options.force:
            print(f"--force: removing files while a server is listening on {options.server}")
        else:
            print(
                f"a SpacetimeDB server is listening on {options.server}; stop it before "
                "`files`, pass --restart-server, or pass --force if it is not yours",
                file=sys.stderr,
            )
            return 1

    result = remove_manifest_files(manifest, data_dir, live_identities, options.apply)
    verb = "removed" if options.apply else "would remove"
    print(f"{verb} {len(result['removed'])} replica directories, {megabytes(result['freed'])}")
    for record in result["skipped"]:
        print(f"skipped {record.get('name')} ({record['reason']})", file=sys.stderr)
    if not options.apply:
        print("dry run: pass --apply to remove these directories")
    if recipe is not None:
        pid = start_standalone_server(recipe, options.server)
        print(f"started server pid {pid}")
        result["restarted_pid"] = pid
    write_json(options.json, {"manifest": str(options.manifest), "files": result})
    return 0


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    if not options.data_dir.is_dir():
        print(f"data dir not found: {options.data_dir}", file=sys.stderr)
        return 1
    if options.action == "files":
        return run_files(options)
    if options.offline:
        if options.action == "entries":
            print("`entries` needs the CLI, so --offline is not supported for it", file=sys.stderr)
            return 2
        return run_report(options, None)
    owned = owned_names(options.spacetime, options.server, options.config_path)
    if options.action == "entries":
        return run_entries(options, owned)
    return run_report(options, owned)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
