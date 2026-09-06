"""Pinned, hash-checked archive access for selected-map imports (stdlib only)."""

import base64
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from fetch_test_assets import METIN_COMMIT, ROOT

API = "https://git.old-metin2.com/api/v1/repos/metin2/client/"


def safe_path(value):
    value = value.replace("\\", "/")
    if value.startswith("/") or any(p in ("", ".", "..") for p in value.split("/")):
        raise ValueError(f"Unsafe archive path: {value!r}")
    if ":" in value or "\0" in value:
        raise ValueError(f"Unsafe archive path: {value!r}")
    return value


def virtual_path(value):
    return safe_path(re.sub(r"^[a-zA-Z]:/", "", value.replace("\\", "/"))).lower()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temp.replace(path)


class Archive:
    def __init__(self, offline=False):
        self.offline = offline
        self.cache = ROOT / ".cache/metin-archive" / METIN_COMMIT
        self.sources = ROOT / "assets/source/maps" / METIN_COMMIT
        self.used = {}
        self.entries = {}
        self.virtual = {}
        self.pack_order = {}

    def request(self, suffix):
        if self.offline:
            raise FileNotFoundError(f"Not cached; retry online: {suffix}")
        request = urllib.request.Request(
            API + suffix, headers={"User-Agent": "mt2spacetime-map-research"}
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    return json.load(response)
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
        raise AssertionError("unreachable")

    def inventory(self):
        def page(number):
            path = self.cache / f"tree-{number}.json"
            if not path.exists():
                data = self.request(f"git/trees/{METIN_COMMIT}?recursive=true&page={number}")
                write_json(path, data)
            return json.loads(path.read_text())

        first = page(1)
        count = first["total_count"]
        size = len(first["tree"])
        with ThreadPoolExecutor(max_workers=6) as pool:
            pages = [first, *pool.map(page, range(2, (count + size - 1) // size + 1))]
        entries = [entry for result in pages for entry in result["tree"]]
        if len(entries) != count or len({e["path"] for e in entries}) != count:
            raise ValueError("Incomplete or duplicate archive inventory")
        self.entries = {safe_path(e["path"]): e for e in entries if e["type"] == "blob"}
        for path in self.entries:
            if path.startswith("bin/pack/") and len(path.split("/")) > 4:
                key = virtual_path(path.split("/", 3)[3])
                self.virtual.setdefault(key, []).append(path)
        print(f"Indexed {len(self.entries)} files at {METIN_COMMIT}", flush=True)
        # RegisterPack inserts without replacement: the first indexed pack wins.
        # See the pinned EterPackManager.cpp and UserInterface.cpp references.
        order = []
        for line in self.get("bin/pack/Index").read_text().splitlines():
            if not line.strip():
                continue
            pack = line.split()[0].lower()
            order.extend((pack, pack + "_texcache"))
        self.pack_order = {name: i for i, name in reversed(list(enumerate(order)))}

    def get(self, path):
        path = safe_path(path)
        entry = self.entries[path]
        destination = self.sources / path
        if destination.exists():
            content = destination.read_bytes()
        else:
            data = self.request(
                "contents/" + urllib.parse.quote(path, safe="/") + "?ref=" + METIN_COMMIT
            )
            if data["sha"] != entry["sha"]:
                raise ValueError(f"Archive metadata mismatch: {path}")
            content = base64.b64decode(data["content"])
        sha = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if sha != entry["sha"]:
            raise ValueError(f"Git blob hash mismatch: {path}; remove the corrupt cached file")
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        self.used[path] = {
            "git_sha": sha,
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }
        return destination

    def resolve(self, name):
        key = virtual_path(name)
        matches = self.virtual.get(key, [])
        if not matches:
            raise FileNotFoundError(f"Unresolved virtual asset: {name}")
        hashes = {self.entries[p]["sha"] for p in matches}
        if len(hashes) > 1:
            ranked = sorted(
                matches, key=lambda p: self.pack_order.get(p.split("/")[2].lower(), 100000)
            )
            rank = self.pack_order.get(ranked[0].split("/")[2].lower(), 100000)
            tied = [
                p for p in ranked if self.pack_order.get(p.split("/")[2].lower(), 100000) == rank
            ]
            if rank == 100000 or len({self.entries[p]["sha"] for p in tied}) > 1:
                raise ValueError(f"Conflicting pack versions for {name}: {matches}")
            return ranked[0]
        return sorted(matches)[0]

    def fetch_many(self, paths):
        with ThreadPoolExecutor(max_workers=6) as pool:
            return list(pool.map(self.get, sorted(set(paths))))
