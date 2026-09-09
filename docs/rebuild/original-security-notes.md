# Original server security notes

These notes record security-relevant behavior observed in the pinned historical
server while implementing the rebuild. They are static findings unless a row says
otherwise. No original binary, service, database, quest, or client from the audit
checkout was executed.

Canonical source:
[`metin2/server` at `7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318).
The ignored checkout is under `.cache/full-game-research/server/source`.

## Risk ledger

| ID | Observation and evidence | Exploitation risk | Rebuild response |
| --- | --- | --- | --- |
| OSS-001 | The pinned README says the tree derives from an old leak and that most public exploits remain **unpatched**. It calls the project a serious security risk. | The exact exploit set is intentionally not enumerated upstream. Assume unknown remote crash, item duplication, privilege, and gameplay-integrity bugs exist. | Never expose or reuse the legacy service. Use the new typed SpacetimeDB protocol, threat model, fuzz/replay tests, least privilege, and explicit migration from legacy accounts rather than protocol compatibility. |
| OSS-002 | `CInputMain::Move` accepts client destination coordinates and only rejects a single packet whose displacement exceeds 25 m on foot or 40 m while riding. It does not validate elapsed time or an authoritative movement budget before `Goto`/`Move`. | A modified client can burst movement, teleport within the allowance, bypass intended pacing, escape combat, or create large position corrections. Packet flooding can amplify the problem. | Clients send bounded movement intents. The server owns position, speed, collision, cooldown, and tick integration, with finite/range validation and a maximum authoritative travel envelope. |
| OSS-003 | `CInputMain::SyncPosition` accepts client-supplied positions for up to 16 other entities and calls `victim->Sync(...)`. It permits a 25 m correction per target and one update per 50 ms, with a small grace counter before disconnect. | A malicious client can move other players or mobs, desynchronize combat, drag targets, grief players, or manipulate line-of-sight and target selection. | Clients never author positions for other entities. Only the authoritative simulation writes world positions; subscriptions distribute server state. Suspicious intent rates are rate-limited and rejected without changing state. |
| OSS-004 | Combat packets carry the victim VID, attack/skill type, and client motion (`CInputMain::Attack`, `Move` skill-motion branch). The server has some skill-motion checks, but the protocol is organized around raw client action packets rather than a single validated action intent. | Modified clients can probe incomplete hit timing, range, target, cooldown, or animation-state checks. Logging a hack is not equivalent to preventing its effect. | Reducers validate identity, target life/action generation, range, height, facing, cooldown, resource cost, phase, and rate before accepting an action. Damage and rewards commit server-side exactly once. |
| OSS-005 | Client packets are parsed by casting raw byte buffers to packed C/C++ structs with `reinterpret_cast` throughout `input_*.cpp`; packet tables validate a base length, while individual handlers perform their own extra-length checks. | Malformed or version-mismatched packets can expose out-of-bounds reads, integer confusion, undefined behavior, or parser crashes. This is a memory-safety class, not proof of a specific exploit. | Use generated typed serialization and explicit schema/application versions. Validate every length and value before use; fuzz parser boundaries and reject malformed input transactionally. |
| OSS-006 | The original account packet carries login credentials to the legacy auth service, and game sessions use a legacy login-key flow (`CInputAuth::Login`, `CInputLogin::LoginByKey`). | Without an independently verified TLS endpoint, credentials and session material can be intercepted or replayed. A compromised account bypasses gameplay protections entirely. | Better Auth over HTTPS, short-lived signed game sessions, issuer/audience validation, refresh/rotation, rate limits, account recovery controls, and no password in the gameplay protocol. |
| OSS-007 | Quests execute in a privileged in-process Lua runtime with hundreds of bindings that can grant items/gold/EXP, change stats/skills/privileges, spawn or purge mobs, warp players, and mutate persistent state. | A bad or malicious quest/content change has server-wide authority. Bugs in content can duplicate rewards, corrupt state, crash the process, or become privilege escalation if publishing is not tightly controlled. | Keep quests/content data-driven but compile and validate them against a capability-scoped API. Use bounded execution, typed IDs/ranges, transactional rewards, versioned state, dry-run diagnostics, and owner-only publishing. |
| OSS-008 | Administration is exposed through a large chat-command table (`cmd.cpp`), including teleport, spawn/item/stat/skill grants, kill/disconnect, reload, event, guild, land, arena, and shutdown operations. Privilege levels are partly runtime-configured. | A compromised staff account, accidental privilege assignment, command-parser bug, or leaked configuration can become full server compromise. Chat commands provide weak structure and auditability. | Separate authenticated admin tooling from gameplay chat. Use RBAC, scoped capabilities, reason/ticket fields, preview/dry-run, idempotency, and immutable before/after audit records. |
| OSS-009 | Persistence is split between game processes, a DB daemon, process-local caches, and write-behind SQL. The source repository does not contain the database schema or constraints. | Crashes, retries, concurrent cores, and partial writes can create lost updates, stale caches, or duplicated items/currency. Trade, exchange, storage, refinement, and reward paths are especially sensitive. | Model ownership and economy mutations as atomic reducers with unique IDs, idempotency keys, server-side definitions, audit rows, and recovery tests covering retry, disconnect, and restart. |
| OSS-010 | The historical tree contains many string-built SQL queries and a broad database daemon surface. Some input paths escape values, but the schema and all call sites cannot be verified from the available source. | Any missed escaping or unsafe dynamic identifier can become SQL injection, data disclosure, or destructive database access. | Use parameterized queries through reviewed adapters, deny dynamic SQL/identifiers from content, separate service credentials, and test authorization/read filters independently of client filtering. |

## Use in the rebuild

These findings are not compatibility requirements. Preserve original presentation,
movement feel, combat pacing, and content where selected, but do not preserve
client authority, raw packet layouts, unrestricted content execution, write-behind
economy mutations, or chat-command administration.

Add a new row here whenever implementation or source research exposes another
security-relevant oddity. Link the concrete source path, describe the exploit
class without publishing a working attack, and record the modern invariant or
test that prevents it.
