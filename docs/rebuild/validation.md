# Planning validation record

Reviewed 2026-09-06 against project baseline
`d1b3bbdea24240e03e5e325549eb5c4bd01a377b`. This records completion of the
research/planning deliverable, not implementation of the full game.

| Requested deliverable | Evidence inspected |
| --- | --- |
| Inspect original server and its feature surface | Pinned server audit; source-family mapping covers 178 game and 30 DB basenames with no unknown/duplicate units; 233 commands, 532 quest bindings in 27 namespaces, 238 selected quests, enums/switches and content inventories |
| Inspect original client, screens and content formats | Pinned client tree with 56,037 blobs; 842 selected source/layout/metadata files Git-blob verified; 171 Python UI paths, 82 CG/128 GC headers; all 64 CLI evidence path/symbol records checked against source |
| Inspect open-mt2 and other implementations | open-mt2, Quantum Core X and narrow NakiuS client comparison pinned; implemented/partial/absent distinctions come from source paths/registries/tests, not only READMEs |
| Account for full systems and overlooked mechanics | 194 catalog records across 41 systems: 58 SRV, 32 CLI, 46 REF and 58 modernization records; 45 additional named server subfeature rows attached to relevant parents; every classic family, marriage/wedding/divorce and conditional source families remain visible |
| Include later features without conflating eras | All 17 linked Systems entries and 86 world destinations from the inspected official-domain index retained; individual later-feature records; missing Merc/Heart of Greed references and fork-specific uncertainty explicit |
| Dependencies and implementation guide | Acyclic system/feature prerequisite graph, preserved behavioral coupling, P0–P10 phases, state machines, per-system gates and work-package checklist |
| Classic feel with modern practices and optimization | Server authority, typed definitions, privacy/interest management, bounded work, measured client/Web performance, migration/recovery and fidelity policies |
| Development/admin tools and automation | General content compiler; model/animation/equipment/map/UI/quest/skill/item/mob/effect/audio workflows; inspectors/simulators/scenarios and authorized audited operator controls |
| Correct GR2 conversion boundary | Explicit build-time GR2→Blender/GLB→Godot-resource flow, no player GR2/Granny/Blender dependency; only current warrior/four-clip coverage claimed |
| Honest source/content completeness | Map crosswalk records 124 literal names and unresolved aliases; active/inactive/conditional/non-executing source paths and missing original evidence remain in the decision/coverage ledger |
| Repository integration and maintainability | README/architecture/development/provenance links, canonical JSON, generated catalog, offline validator and `make check-plan` included in `make check` |

## Checks performed

- `python3 tools/dev.py lint` passed all configured scopes. After subsequent
  planning-checker changes, Python correctness/format checks passed again.
- `make check-plan` validates 41 systems/194 records, known IDs/evidence
  repositories/phases, required fields, prerequisite acyclicity, referenced
  inventories and exact generated-document agreement.
- Nine in-memory negative fixtures reject duplicate IDs, unknown prerequisites,
  cycles, unpinned evidence, completion without evidence, missing inventories,
  omitted system prerequisites, unknown coupling IDs and incomplete subfeatures.
  A future complete status with explicit evidence is structurally supported.
- Local Markdown file/anchor links were checked with no failures. Immutable
  source evidence was checked against research snapshots; independent review
  found and fixed one stale QCX path and an incorrect skill-registry summary.
- JSON inventory counts and source responsibility coverage were cross-checked;
  the command sentinel was excluded, correcting the final command count to 233.
- `git diff --check` passed. Research snapshots, source bodies, asset bytes,
  account/session material and local test reports stay ignored.

The checker validates planning structure, not the truth of arbitrary evidence
text. Review still owns source interpretation and completion decisions. Existing
gameplay reports were inspected; no new gameplay integration, original-client
execution, deployment, database mutation or asset conversion was performed in
this planning pass. Full `make check`/engine/export runs are not claimed here:
the changed executable is the offline planning validator, which was directly
exercised with valid and invalid inputs.

Remaining unknowns in [coverage-and-decisions.md](coverage-and-decisions.md)
are part of the implementation guide: exact retail/profile alignment, original
captures, unparsed asset variants, missing content and live modern rules need
their specified evidence before implementation/parity claims. No claim is made
to have verified every historical release, private fork, source line or quest
branch.
