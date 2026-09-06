"""Validate and render the source-backed rebuild planning catalog (no network access)."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/rebuild/plan.json"
OUTPUT = ROOT / "docs/rebuild/feature-catalog.md"


def validate(plan: dict) -> dict[str, dict]:
    """Reject incomplete IDs, unknown prerequisites and cyclic implementation order."""
    if plan.get("schema_version") != 1:
        raise ValueError("Unsupported planning schema")
    if not plan.get("sources") or not plan.get("coverage"):
        raise ValueError("Source provenance and coverage are required")
    systems = plan.get("systems", [])
    features = plan.get("features", [])
    if not systems or not features:
        raise ValueError("Systems and features must be nonempty")
    nodes: dict[str, dict] = {}
    phases = set(plan.get("phases", []))
    source_ids = {source["id"] for source in plan["sources"]}
    for node in systems + features:
        identifier = node.get("id")
        if not identifier or identifier in nodes:
            raise ValueError(f"Missing or duplicate ID: {identifier}")
        if not node.get("name") or not isinstance(node.get("depends_on"), list):
            raise ValueError(f"Missing name/dependency list: {identifier}")
        nodes[identifier] = node
    system_ids = {node["id"] for node in systems}
    for node in systems:
        if node.get("first_phase") not in phases or not node.get("acceptance"):
            raise ValueError(f"Missing system phase/acceptance: {node['id']}")
    for node in features:
        identifier = node["id"]
        if node.get("system") not in system_ids:
            raise ValueError(f"Unknown system for {identifier}")
        if node["system"] not in node["depends_on"]:
            raise ValueError(f"Feature omits its system prerequisite: {identifier}")
        if node.get("phase") not in phases:
            raise ValueError(f"Unknown phase for {identifier}")
        for field in ("scope", "project_status", "notes", "evidence"):
            if not node.get(field):
                raise ValueError(f"Missing {field} for {identifier}")
        if node["project_status"] not in {
            "planned",
            "partial",
            "reference-only",
            "decision",
            "complete",
        }:
            raise ValueError(f"Invalid project status for {identifier}")
        if node["project_status"] == "complete" and not node.get("completion_evidence"):
            raise ValueError(f"Completion requires scoped acceptance evidence: {identifier}")
        for evidence in node["evidence"]:
            if not evidence.get("path"):
                raise ValueError(f"Missing evidence path: {identifier}")
            if evidence.get("repo") and not evidence.get("commit"):
                raise ValueError(f"Unpinned repository evidence: {identifier}")
            if evidence.get("repo") and evidence["repo"] not in source_ids:
                raise ValueError(f"Unknown evidence repository: {identifier}")
        for related in node.get("behavior_dependencies", []):
            if related.startswith(("SRV-", "CLI-", "REF-", "MOD-", "SYS-")):
                if related not in nodes:
                    raise ValueError(f"Unknown behavioral feature {related} in {identifier}")
        for subfeature in node.get("subfeatures", []):
            if not subfeature.get("name") or not subfeature.get("contract"):
                raise ValueError(f"Incomplete named subfeature in {identifier}")
    for identifier, node in nodes.items():
        for dependency in node["depends_on"]:
            if dependency not in nodes:
                raise ValueError(f"Unknown dependency {dependency} in {identifier}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise ValueError(f"Dependency cycle at {identifier}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in nodes[identifier]["depends_on"]:
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in nodes:
        visit(identifier)
    for item in plan["coverage"]:
        path = ROOT / "docs/rebuild" / item["inventory"]
        if not path.is_file():
            raise ValueError(f"Missing inventory: {path}")
        json.loads(path.read_text())
        for identifier in item["feature_ids"]:
            if identifier not in nodes:
                raise ValueError(f"Unknown coverage feature: {identifier}")
    return nodes


def cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def link(identifier: str) -> str:
    return f"[{identifier}](#{identifier.lower()})"


def evidence_link(entry: dict, sources: dict) -> str:
    path = entry["path"]
    url = entry.get("url")
    if not url and path.startswith(("https://", "http://")):
        url = path
    if not url and entry.get("repo") in sources:
        source = sources[entry["repo"]]
        url = source["file_url"].format(commit=entry["commit"], path=quote(path, safe="/"))
    if not url:
        url = path
    label = entry.get("symbol") or path.rsplit("/", 1)[-1]
    label = cell(label).replace("[", "(").replace("]", ")")
    return f"[{label}]({url})"


def render(plan: dict, nodes: dict[str, dict]) -> str:
    features = plan["features"]
    sources = {source["id"]: source for source in plan["sources"]}
    counts = Counter(feature["project_status"] for feature in features)
    lines = [
        "# Full-game feature and dependency catalog",
        "",
        "Generated from [plan.json](plan.json) by `python3 tools/check_rebuild_plan.py --write`.",
        "Edit the JSON source, then regenerate. Validate with `python3 tools/check_rebuild_plan.py`.",
        "",
        f"This catalog contains **{len(features)} records across {len(plan['systems'])} systems**.",
        "Server requirements, client requirements, reference comparisons and modernization tasks",
        "can describe different parts of the same gameplay system; this is not a count of unique",
        "game mechanics or a percentage-complete estimate.",
        "",
        "Project status: "
        + ", ".join(f"{key} {value}" for key, value in sorted(counts.items()))
        + ".",
        "`partial` means only the documented current slice exists. `complete` requires",
        "scoped acceptance evidence; the checker cannot establish its semantic sufficiency.",
        "`reference-only` records evidence or legacy infrastructure to replace.",
        "`decision` keeps an optional/uncertain source capability visible pending rules-profile",
        "selection. `planned` requires implementation. Upstream implementation status is separate.",
        "",
        "The **implementation prerequisites** form an acyclic graph. A feature depends on its",
        "system foundation and any additional listed system/feature. **Behavioral coupling**",
        "preserves the source audit's interactions; it can contain cycles and is not a build order.",
        "System gates apply to every feature in that system together with the feature's detailed",
        "behavior and [work-package checklist](architecture-and-delivery.md#work-packages-and-realistic-planning).",
        "Phase labels identify first delivery/integration; completing a whole family can span",
        "several phases. See [delivery phases](architecture-and-delivery.md#delivery-phases-and-gates).",
        "",
        "## System dependencies and acceptance gates",
        "",
        "| System | First phase | Implementation prerequisites | Acceptance |",
        "| --- | --- | --- | --- |",
    ]
    for system in plan["systems"]:
        deps = ", ".join(link(dep) for dep in system["depends_on"]) or "None"
        lines.append(
            f"| {link(system['id'])}: {cell(system['name'])} | {system['first_phase']} "
            f"| {deps} | {cell(system['acceptance'])} |"
        )
    for system in plan["systems"]:
        lines += ["", f"## {system['id']}", "", system["name"], ""]
        for feature in features:
            if feature["system"] != system["id"]:
                continue
            lines += [
                f"### {feature['id']}",
                "",
                f"**{feature['name']}** — {feature['project_status']}; {feature['phase']}.",
                "",
                "Scope: " + feature["scope"].rstrip(".") + ".",
                "",
                feature["notes"],
                "",
                "Implementation prerequisites: "
                + ", ".join(link(x) for x in feature["depends_on"])
                + ".",
            ]
            coupled = feature.get("behavior_dependencies", [])
            if coupled:
                lines += [
                    "",
                    "Behavioral coupling: "
                    + ", ".join(link(x) if x in nodes else cell(x) for x in coupled)
                    + ".",
                ]
            if feature.get("current_evidence"):
                lines += ["", "Current project: " + feature["current_evidence"]]
            if feature.get("completion_evidence"):
                lines += ["", "Completion evidence: " + feature["completion_evidence"]]
            if feature.get("subfeatures"):
                lines += ["", "Named subfeatures and required behavior:", ""]
                for subfeature in feature["subfeatures"]:
                    lines.append(f"- **{subfeature['name']}:** {subfeature['contract']}")
            lines += [
                "",
                "Evidence: "
                + "; ".join(evidence_link(entry, sources) for entry in feature["evidence"])
                + ".",
                "",
            ]
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerate the Markdown catalog")
    args = parser.parse_args()
    try:
        plan = json.loads(PLAN.read_text())
        nodes = validate(plan)
        result = render(plan, nodes)
        if args.write:
            OUTPUT.write_text(result)
        elif not OUTPUT.is_file() or OUTPUT.read_text() != result:
            raise ValueError("Catalog is stale; run python3 tools/check_rebuild_plan.py --write")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Rebuild plan: {error}\n")
    print(f"Rebuild plan valid: {len(plan['systems'])} systems, {len(plan['features'])} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
