"""Compare generated content pairs and report which verification scope changed."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

SERVER_SCHEMA = "mt2spacetime.trusted-action-definitions"
CLIENT_SCHEMA = "mt2spacetime.presentation-manifest"
SERVER_METADATA = {"content_hash", "gameplay_definition_hash"}
CLIENT_METADATA = SERVER_METADATA | {"presentation_output_hash"}


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_number(value: str) -> None:
    raise ValueError(f"Non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        _invalid_number(value)
    return result


def _load(path: Path) -> dict:
    result = json.loads(
        path.read_text(),
        object_pairs_hook=_unique_object,
        parse_constant=_invalid_number,
        parse_float=_finite_float,
    )
    if not isinstance(result, dict):
        raise ValueError(f"Expected a content object: {path}")
    return result


def _validate_pair(server: dict, client: dict) -> None:
    if (
        server.get("schema") != SERVER_SCHEMA
        or type(server.get("schema_version")) is not int
        or server["schema_version"] not in (5, 6, 7)
    ):
        raise ValueError("Content diff supports trusted-definition schemas 5, 6 and 7")
    if (
        client.get("schema") != CLIENT_SCHEMA
        or type(client.get("schema_version")) is not int
        or client["schema_version"] != 1
    ):
        raise ValueError("Content diff supports presentation-manifest schema 1")
    for key in ("profile_id", "content_hash", "gameplay_definition_hash"):
        if (
            not isinstance(server.get(key), str)
            or not server[key]
            or server[key] != client.get(key)
        ):
            raise ValueError(f"Client/server pair disagrees on {key}")
    payload = {key: value for key, value in server.items() if key != "gameplay_definition_hash"}
    if _digest(payload) != server["gameplay_definition_hash"]:
        raise ValueError("Trusted-definition digest does not match its payload")
    if not isinstance(client.get("artifacts"), list):
        raise ValueError("Presentation manifest has no artifact list")
    if _digest(client["artifacts"]) != client.get("presentation_output_hash"):
        raise ValueError("Presentation-output digest does not match its artifact records")


def _pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _changes(before: object, after: object, path: str = "") -> list[dict]:
    if type(before) is not type(after):
        return [{"path": path or "/", "change": "type"}]
    if isinstance(before, dict):
        changes = []
        for key in sorted(before.keys() | after.keys()):
            child = path + "/" + _pointer(key)
            if key not in before or key not in after:
                changes.append({"path": child, "change": "added" if key in after else "removed"})
            else:
                changes.extend(_changes(before[key], after[key], child))
        return changes
    if isinstance(before, list):
        # Preserve order: combo lists and other authored sequences are semantic.
        changes = []
        for index in range(max(len(before), len(after))):
            child = path + "/" + str(index)
            if index >= min(len(before), len(after)):
                changes.append(
                    {"path": child, "change": "added" if index < len(after) else "removed"}
                )
            else:
                changes.extend(_changes(before[index], after[index], child))
        return changes
    return [] if before == after else [{"path": path or "/", "change": "value"}]


def compare_pairs(before_server: dict, before_client: dict, after_server: dict, after_client: dict):
    """Compare actual fields; declared hashes alone never classify a change as safe."""
    _validate_pair(before_server, before_client)
    _validate_pair(after_server, after_client)
    gameplay = _changes(
        {key: value for key, value in before_server.items() if key not in SERVER_METADATA},
        {key: value for key, value in after_server.items() if key not in SERVER_METADATA},
    )
    presentation = _changes(
        {key: value for key, value in before_client.items() if key not in CLIENT_METADATA},
        {key: value for key, value in after_client.items() if key not in CLIENT_METADATA},
    )
    metadata = before_server != after_server or before_client != after_client
    category = (
        "gameplay-and-presentation"
        if gameplay and presentation
        else "gameplay"
        if gameplay
        else "presentation"
        if presentation
        else "provenance"
        if metadata
        else "unchanged"
    )
    checks = []
    if gameplay or presentation or metadata:
        checks.append("Validate the changed generated content and its pinned inputs.")
    if gameplay:
        checks.append(
            "Run affected mechanic tests and actual two-client gameplay/lifecycle checks."
        )
    if presentation:
        checks.append(
            "Inspect affected assets, animation/attachments and rendered Godot appearance."
        )
        checks.append("Check the affected exported format when its rendering or packaging changes.")
    return {
        "schema": "mt2spacetime.content-change-report",
        "schema_version": 1,
        "category": category,
        "profiles": {"before": before_server["profile_id"], "after": after_server["profile_id"]},
        "gameplay_changes": gameplay,
        "presentation_changes": presentation,
        "recommended_checks": checks,
        "limits": [
            "Comparison is QA guidance, not content validation or an acceptance result.",
            "Artifact records are compared; referenced asset bytes are not opened by this command.",
            "Code, protocol and map-bake changes require their own verification scope.",
            "Account lifecycle/refresh checks are needed when those contracts change or at release.",
        ],
    }


def add_parser(subparsers) -> None:
    parser = subparsers.add_parser("diff", help="compare content pairs and select affected QA")
    for name in ("before-server", "before-client", "after-server", "after-client"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.set_defaults(function=diff_command)


def diff_command(args) -> None:
    paths = (args.before_server, args.before_client, args.after_server, args.after_client)
    if args.output and args.output.resolve() in {path.resolve() for path in paths}:
        raise ValueError("The report output must not overwrite a content input")
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    report = compare_pairs(*[_load(path) for path in paths])
    if hashes != [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]:
        raise ValueError("Content inputs changed during comparison; retry with stable snapshots")
    report["inputs"] = [
        {"path": str(path), "sha256": digest} for path, digest in zip(paths, hashes, strict=True)
    ]
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")
