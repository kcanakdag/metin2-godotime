# Working in this repository

Build a modern Metin2-like game with a lightweight Godot client and a SpacetimeDB
server. Keep the familiar movement, camera, characters, and pacing. The immediate
baseline is a shared development map; implement features as small vertical slices
that can be exercised by two real clients. Read `README.md`, `docs/architecture.md`,
and `docs/development.md` before changing the architecture or run workflow.

## Ownership and contracts

- The server owns identity, presence, movement limits, gameplay state, and action
  validation. Clients send intents; they cannot grant themselves positions,
  damage, items, currency, or permissions. Validate client numbers for finite
  values and expected ranges before using them.
- Keep protocol/database changes synchronized with the client and multiplayer
  smoke test. Include reducer rejection, reconnect, and disconnect behavior when
  those paths change. Never treat a locally animated avatar as evidence of server
  movement or a queried database row as evidence of client subscriptions.
- Keep production gameplay separate from developer inspection and controls. Do
  not ship the editor MCP bridge, runtime script evaluator, identity tokens,
  local logs, or source asset archives in a friend/release build. Debug menus may
  inspect state and send normal validated actions; privileged actions need
  server-side authorization.
- Preserve the standard Godot/GDScript path unless an evidenced requirement
  justifies an engine/distribution change. Keep dependencies pinned and document
  any SpacetimeDB protocol version assumption.

## Changes and tools

- Use `python3 tools/dev.py setup` once, then `python3 tools/dev.py lint` and the
  relevant `make` checks. `python3 tools/dev.py format` applies formatters and
  Ruff's safe fixes only to owned sources. See `docs/development.md` for scopes.
  Fix findings instead of disabling checks globally; explain narrow exceptions.
- Python uses Ruff, GDScript uses gdformat/gdlint and the real Godot parser,
  Rust uses rustfmt/clippy/tests, and the Node MCP bridge uses its strict
  TypeScript configuration and dependency lock. A linter pass alone does not
  establish that the editor or exported game works.
- Keep changes scoped. Do not reformat vendored `client/addons/godot_mcp` or
  `tools/godot-mcp-server` wholesale. Document necessary upstream patches in the
  existing provenance files. Do not edit generated `.godot`, build, cache, or
  downloaded source files as a substitute for fixing the generator.
- Use Godot MCP to inspect the connected project, current scene, runtime tree,
  rendered game screenshot, and relevant input behavior for visual/input changes.
  Confirm the project path before mutating the editor. Preserve unrelated open
  scenes and unsaved work. Record observed results and remaining limitations.
- Keep the MCP bridge local. Do not start a second MCP server on its active port.
  Use a separate data directory/database name for disposable multiplayer tests;
  never overwrite or wipe an existing development database to make tests pass.

## Evidence and assets

- For network changes, verify two independent identities on one actual server:
  both see each other, each can move, remote movement updates, and a disconnect
  removes presence. Add reconnect coverage when touching connection lifecycle.
- For friend builds, run the actual export command, inspect packaged contents,
  and test an exported client against the intended endpoint. Distinguish local
  connectivity from verified internet reachability and Linux tests from Windows
  execution; document any platform or network requirement that remains.
- Use the Blender conversion tools and pinned inputs for asset work. Keep
  original assets, converted derivatives, and downloaded third-party code in
  their ignored directories. Preserve commit/hash provenance. Test animation
  deformation and the Godot appearance when changing import logic.
- Consult `docs/third-party.md` before copying external code. A source reference
  is not a license grant; GPL reference implementations and original Metin2
  assets have different terms from MIT tooling. Do not silently import an entire
  external project or expand the fixture set to every game asset.
- Update the README and relevant architecture/development notes when commands,
  gameplay contracts, dependencies, controls, or export behavior change. Report
  what was actually tested, including concrete missing end-to-end evidence.
