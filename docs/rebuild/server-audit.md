# Original server and content audit

This audit inventories the historical C++ server and its bundled server-side
content as reconstruction evidence. It is not a recommendation to port that
architecture. The rebuild should preserve the selected game experience while
using the repository's authoritative SpacetimeDB model, typed contracts,
transactions, subscriptions, secure account boundary, repeatable content builds,
and audited administration.

Security-relevant oddities found during implementation are tracked separately in
the [original server security notes](original-security-notes.md). They record
exploit classes and the modern invariant that replaces the unsafe behavior.

## Evidence boundary

The canonical source inspected is
[`metin2/server` at `7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318),
tagged `0.4.1` on protected `master`. It was retrieved on 2026-09-06 with a
shallow Git clone into ignored `.cache/full-game-research/server/source`. No
source, script, binary, or game service from that checkout was executed. The
tracked [server inventory](evidence/server-inventory.json) records the exact pin,
retrieval method, all source-unit names, command rows, native quest APIs, feature
switch occurrences, packet/enum names, quest selection, maps, monster motion
directories, and data catalogs. It also groups all 178 unique game-source and 30
DB-daemon basenames by primary responsibility, SRV IDs and rebuild disposition;
the mechanical mapping currently leaves no basename in its explicit unknown
bucket. Low-level transport, event, allocation and parser groups are marked for
replacement or supporting use rather than inflated into gameplay features.

The source README describes a 2014-oriented preservation target, says its
`gamefiles` came from a 2023-08-05 40k reference set, and explicitly warns that
many known exploits remain unpatched. It also contains no license file. That
combination has three consequences:

- Treat it as behavioral and inventory evidence, not a secure implementation or
  a redistribution grant.
- Do not call every included system "classic." Dragon Soul, costumes, belts,
  pets, flame content, level 99-105 quests, and other later additions need a
  selected release/profile before they enter the baseline.
- Do not claim parity with the current live game. This is one historical tree,
  with incomplete and inactive material, not an authoritative modern catalog.

The checkout has 7,692 tracked files. Its owned executable-side source includes
277 game files, 50 DB-daemon files, 14 shared-contract files and three quest
compiler files. The embedded Lua 5-era source and low-level event, networking,
SQL and formula libraries are recorded in the ledger so their responsibilities
are not lost, but they are deliberately replaced infrastructure.

## What the old server actually is

The original topology is three roles built from two binaries: auth and game
roles use the game executable, while a separate DB daemon loads SQL-backed
tables, caches characters/items, allocates item IDs, and relays state among game
cores. The relevant boundaries are
[`CInputAuth`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_auth.cpp),
[`CInputLogin`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_login.cpp),
[`CInputMain`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_main.cpp),
[`CInputP2P`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_p2p.cpp), and
[`CInputDB`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/input_db.cpp).

The contracts are raw packed structures and numeric headers. The inspected
registries contain 184 client/game header tokens, 25 game-peer tokens, 188
game/DB tokens, and 25 DB query IDs. They cover character entry, movement,
combat, items, shops, exchange, quests, parties, guilds, fishing, refining,
storage, marks, affects, Dragon Soul, presence, marriage/weddings, monarch
elections, cash awards and channel status. See
[`packet.h`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/packet.h),
[`tables.h`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/common/tables.h), and
[`QID.h`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/QID.h).
These token lists are discovery aids. The new protocol must use generated typed
bindings, stable IDs, explicit schema/application versions, finite/range checks,
authorization and transactions; it must not reproduce compiler-dependent struct
layouts, P2P globals or write-behind cache behavior.

The shared enums expose a second coverage registry. `length.h` defines jobs,
skill groups, wear positions, chat/whisper and GM levels, character/mob/battle
types, 93 apply entries, AI/immunity/enchant/resist flags, guild-war states,
privileges, money logs and premium types. `item_length.h` defines 35 item types
plus weapon, armor, costume, Dragon Soul, fish, resource, use, material, flag,
anti-flag, wearable, limit and refine subtypes. The machine ledger keeps every
parsed member name. These are definition inputs, not proof that corresponding
content is enabled or complete.

## Feature coverage ledger

The following IDs are stable within this planning audit. The
[canonical plan](plan.json) contains 58 `SRV-*` entries with scope, evidence,
notes and dependencies. This table keeps every family visible in the tracked
plan and points to representative symbols. Its `behavior_dependencies` values
record observed behavioral and integration coupling.
They intentionally contain cycles such as stats/skills/combat/affects and are
not an implementation build DAG; the implementation roadmap must derive an
acyclic prerequisite graph from these coupled contracts.

| IDs | Scope and systems | Representative original evidence | Rebuild dependency or decision |
| --- | --- | --- | --- |
| SRV-001-SRV-006 | Process/protocol, accounts/login keys, character roster, presence/channels, maps/sectrees/portals, movement/sync/warps | `CInput*`, `P2P_MANAGER`, `SECTREE_MANAGER`, `CMapLocation` | Keep Better Auth and SpacetimeDB authority; add explicit map/instance membership, intent sequences, correction, reconnect and disconnect cleanup. |
| SRV-007-SRV-010 | EXP/levels/stats/alignment, player/guild/horse skills, combat/death/respawn, affects/buffs/debuffs/resists | [`char_battle.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_battle.cpp), [`char_skill.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_skill.cpp), `CHARACTER::PointChange`, `AddAffect` | Pin formulas and caps to a chosen release; server validates range, target, cooldown, resource, phase and state. |
| SRV-011-SRV-012 | Mob/NPC definitions, AI, groups, regen/spawns, drops, ground items and loot ownership | [`CMobManager::Initialize/LoadGroup`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/mob_manager.cpp), [`regen_load`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/regen.cpp), `ITEM_MANAGER::CreateDropItem` | Compile validated definitions/spawn regions/drop distributions; test ownership, expiration and duplicate/replayed kills. |
| SRV-013-SRV-015 | Item instances, bag/windows, equipment/quickslots, attributes/sockets and all refine paths | [`char_item.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_item.cpp), `CItem`, `CRefineManager`, `item_attribute.cpp` | One transaction per ownership/slot/currency mutation; validated definitions, recipes and upgrade graphs. |
| SRV-016-SRV-020 | NPC and extended shops, private shops, direct exchange, safebox/mall, gold/premium/cash/awards/economy logs | `CShopManager`, `CExchange`, `CSafebox`, `CMoneyLog`, `pc_charge_cash` | Atomic transfers, locks/idempotency, private reads, source/sink ledger, overflow/cap rules and audited external grants. |
| SRV-021-SRV-025 | Parties, chat/messenger/blocking, guild membership/ranks/skills/funds, guild wars/reservations/bets, guild land/buildings/castle/siege | [`party.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/party.cpp), [`guild.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/guild.cpp), [`guild_war.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/guild_war.cpp), [`building.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/building.cpp) | Explicit membership/role permissions, atomic treasury and construction, deterministic war lifecycle/settlement, disconnect/rejoin rules. |
| SRV-026-SRV-027 | Open-world PvP/PK/alignment/duels, arena observers and scheduled battle arena | `CPVPManager`, `CArenaManager`, `CBattleArena` | Release-specific rules, authoritative eligibility/scoring, match lifecycle and recovery. |
| SRV-028-SRV-030 | Quest compiler/VM/state/timers/event flags, NPC dialogue/targets, private dungeon instances | [`CQuestManager`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questmanager.cpp), [`quest compiler`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/quest/src/qc.cc), `CDungeonManager`, `TargetManager` | Sandboxed/versioned content execution or typed workflows, bounded timers, validated rewards and recoverable instance membership. |
| SRV-031-SRV-033 | Devil Tower/catacomb/spider content, Blue Dragon/Dragon Lair, flame dungeon and levels 99-105 | `deviltower_zone.quest`, `devilcatacomb_zone.quest`, `BlueDragon.cpp`, `DragonLair.cpp`, `flame_dungeon.quest` | Profile later dungeon packs independently; source presence does not establish completeness or classic inclusion. |
| SRV-034-SRV-036 | Engagement/marriage/love points/couple items, wedding instance and ceremony, divorce/forced break | [`marriage::CManager`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/marriage.cpp), [DB marriage manager](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/Marriage.cpp), [`WeddingMap`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/wedding.cpp), `marriage_remove`, `do_break_marriage` | Atomic two-character relationship state, costs, buffs, partner warp, private ceremony membership/guests and complete cleanup on divorce/disconnect. |
| SRV-037-SRV-043 | Horse, special mounts, pets, fishing, mining, polymorph and cube crafting | `CHorseRider`, `CPetSystem`, `fishing::Take`, `mining`, `CPolymorphUtils`, `Cube_make` | Horse is core; mounts/pets/recipes are selectable content capabilities. Server timers, RNG and item costs remain authoritative. |
| SRV-044-SRV-045 | Dragon Soul alchemy/inventory/decks, costumes, belts, energy and hair | [`DSManager`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/DragonSoul.cpp), `CBeltInventoryHelper`, `energy_system.quest` | Later expansion profiles with separate schema/content gates; never let a client grant effects or refinement outcomes. |
| SRV-046-SRV-049 | Monarch candidacy/elections/treasury/tax/powers, empire rules/privileges, three-way/empire wars, OX and seasonal/live events | [`CMonarch`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/monarch.cpp), [`questlua_monarch.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua_monarch.cpp), `CThreeWayWar`, `COXEventManager`, `xmas_event.cpp` | Product decision for monarch and event variants; audited schedules, idempotent operations and crash/restart recovery. |
| SRV-050-SRV-054 | Localization/profanity, GM/liveops, persistence/caches/logging, content import/validation, security/anti-abuse | locale service and translated catalogs, `cmd_info`, `CClientManager::InitializeTables`, `CSequence` | UTF-8/key validation, RBAC admin APIs, migrations/RLS/telemetry, reproducible compilers, threat model/fuzz/replay tests. |
| SRV-055 | Auction/wish/sale boards | `AuctionManager` exists in game and DB but [`__AUCTION__` is commented out](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/common/service.h) | Disabled on the pinned baseline. If selected later, redesign listing escrow, expiry and settlement transactionally. |
| SRV-056 | Speed Server EXP schedules | `CSpeedServerManager` and `speedserver` quest API exist; the master EXP hook is commented | Incomplete on master. The separate [`enable-speed-server` commit](https://git.old-metin2.com/metin2/server/commit/e488f5a2444bae9bcb7ac30e1fcab0165d14d3e9) is branch-only evidence. |
| SRV-057-SRV-058 | Guild mark/symbol storage and server motion/hit metadata | `CGuildMarkManager`, guild upload/CRC packets, [`CMotion::LoadMobSkillFromFile`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/motion.cpp) | Bounded/moderated object storage; one automated animation build emits client clips and server timing/hit contracts. |

Marriage is therefore three separate deliverables rather than a checkbox:
relationship state and benefits (SRV-034), the wedding-map ceremony (SRV-035),
and divorce/forced cleanup (SRV-036). Guilds likewise divide into membership and
permissions, wars and settlement, and land/buildings. Monarch elections, empire
wars and seasonal live events have independent state machines and operational
needs.

## Gameplay subfeature checklist

The broad IDs above are portfolio groupings, not implementation-sized features.
The following checklist is derived from a runtime dispatch/handler or a quest in
the pinned `locale_list`; an enum name by itself is not enough. Exact command,
quest-API and enum names remain reproducibly enumerable in the machine ledger.
Rules and numbers still need comparison with the selected classic region and
release before they become acceptance criteria.

### Progression, skills, horses and polymorph

| Parent ID | Named subfeature | Execution evidence and planning obligation |
| --- | --- | --- |
| SRV-007/SRV-008 | Class skill-tree choice and skill-point advancement | Selected [`skill_group.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/skill_group.quest) chooses one of two groups for each of the four jobs; `CHARACTER::SetSkillGroup`, `SkillLevelUp` and the player `skillup` command apply it. Preserve teacher/level gates, point costs, active/passive distinctions and skill-group state. |
| SRV-008 | Normal, Master, Grand Master and Perfect Master ranks | [`char_skill.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_skill.cpp) uses `SKILL_MASTER`, `SKILL_GRAND_MASTER`, `SKILL_PERFECT_MASTER`, `LearnSkillByBook` and `LearnGrandMasterSkill`. Model rank transitions, forced promotion rules, failed/successful reads, EXP consumption, read counters and server deadlines explicitly. |
| SRV-008 | Skill books, read-delay bypass and concentrated-reading bonus | `CHARACTER::UseItemEx` dispatches `ITEM_SKILLBOOK`; `LearnSkillByBook` checks learnability, rank, EXP and next-read time and consumes `AFFECT_SKILL_NO_BOOK_DELAY`/`AFFECT_SKILL_BOOK_BONUS`. These consumable effects, success RNG and failure consumption are separate test branches. |
| SRV-008/SRV-026 | Soul Stone Grand Master training | Selected [`training_grandmaster_skill.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/training_grandmaster_skill.quest) handles item 50513, whose English catalog name is `Soul Stone`; it selects eligible G skills, applies cooldown and alignment cost, calls `pc.learn_grand_master_skill`, and reaches level 40/P. Do not merge this with ordinary books. |
| SRV-008/SRV-021 | Leadership, party roles, summon and heal | `SKILL_LEADERSHIP` has three training-book tiers in `char_item.cpp`. [`party.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/party.cpp) gates attacker, haste, tanker, buffer, skill-master and defender roles, party heal and leader summon by leadership. Each role bonus, assignment permission and proximity/disconnect rule needs coverage. |
| SRV-008/SRV-022 | Empire languages and Language Ring | `SKILL_LANGUAGE1..3` are trained by items 50311-50313; `CInputMain::Chat`/`Whisper` use language skill power when converting other-empires' text, while the Language Ring unique group bypasses it. Keep language comprehension separate from localization and chat moderation. |
| SRV-008/SRV-009/SRV-058 | Combo mastery and attack-chain timing | Items 50304-50306 train `SKILL_COMBO` with level gates; `CHARACTER::SetSkill` selects the combo index. [`ani.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/ani.cpp) loads weapon and mounted combo timings. Compile combo order, cancel/link windows and server hit timing with the corresponding animation profile. |
| SRV-008/SRV-037 | Horse summon and mounted-combat skills | `skill.h` and `char_skill.cpp` implement horse summon plus Wild Attack, Charge, Escape and ranged Wild Attack; the Horse Riding Manual awards bounded riding points. Preserve job restrictions, SP/cooldown/riding requirements and point allocation. |
| SRV-008/SRV-041/SRV-042 | Auxiliary trained skills | Live item branches train polymorph, maximum-HP, penetration-resistance, creation, mining and horse skills. Profile each because their books and values can exist independently of a classic content selection. |
| SRV-007/SRV-008 | Stat, skill-group and single-skill reset | Selected `reset_status.quest` and `skill_reset2.quest` call `pc.reset_status`, `pc.clear_skill` and `pc.set_skill_group`; `ITEM_SKILLFORGET` lowers one skill. `reset_scroll.quest` is present but not selected. Treat NPC, item, level/cost/cooldown variants as distinct flows rather than one generic respec. |
| SRV-037 | Horse acquisition, leveling, grades, health/stamina and naming | Selected `horse_levelup`, `horse_upgrade`, `horse_upgrade2`, `horse_guard`, `horse_menu`, `horse_summon`, `horse_revive`, `horse_ride` and ticket-exchange quests cover mounted trials, grade items, summon items, feed, death/revive, ride/unsummon, status and naming. However, `pony_buy.quest` and `pony_levelup.quest` are present but absent from `locale_list`, so this snapshot does not prove a complete initial acquisition path. |
| SRV-038 | Timed/event mounts versus persistent horse | Selected `ride`, `ride_upgradable`, `ride_ticket_change`, `training_mount` and seasonal ride quests use timed mount affects/items; these are a separately profile-gated system from `CHorseRider` progression and horse skills. |
| SRV-042 | Polymorph balls, books and removal | [`CHARACTER::ItemProcess_Polymorph`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_item.cpp) validates target mob/level, duration/bonus and item subtype; `CPolymorphUtils` updates book practice, while quest APIs expose apply/remove. Define equipment, skill/stat, mount, item-read and death interactions while transformed. |

### Death, PvP, observers and player controls

| Parent ID | Named subfeature | Execution evidence and planning obligation |
| --- | --- | --- |
| SRV-009 | Dead state, delayed restart and forced town return | `dead_event`, `CHARACTER::Dead` and [`do_restart`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/cmd_general.cpp) implement a timed dead phase plus `restart_here` and `restart_town`. Model these as server states; validate late/duplicate requests and reconnect while dead. |
| SRV-009/SRV-030/SRV-048 | Context-specific revive | `do_restart` has separate ordinary-map, guild-war, dungeon, Three-Way War and Sungzi/token paths, with different positions and HP/SP restoration. `ReviveInvisible(5)` supplies temporary post-revive protection on applicable paths. Preserve the selected rules instead of using a universal respawn. |
| SRV-007/SRV-009 | EXP death penalty and protections | `CHARACTER::DeathPenalty` exempts levels below 10, has a luck branch, consumes `AFFECT_NO_DEATH_PENALTY` on applicable here-revives, caps loss, halves it for a unique item and makes the shown town-revive loss zero. Pin the regional table and exact eligibility before implementing. |
| SRV-009/SRV-012/SRV-026 | Alignment-based inventory/equipment drops | [`CHARACTER::ItemDropPenalty`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/char_battle.cpp) selects inventory/equipment probabilities and quantities by alignment band, respects anti-drop flags/protection item, and excludes low levels, shops and battle arena. It is invoked for eligible non-duel/non-war/non-event player deaths. Item removal, ownership and ground-drop placement must be atomic. |
| SRV-026 | Peace, revenge, free, protect and guild PK modes | `CHARACTER::SetPKMode` and [`CPVPManager`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/pvp.cpp) apply empire, guild, map and alignment rules for `PK_MODE_*`. Revenge mode is real behavior, not just a UI label. Define safe-map and level/protection boundaries per profile. |
| SRV-026 | Duel request/agreement/fight/revenge lifecycle | `CPVP::Agree`, `Win` and packet `PVP_MODE_NONE/AGREE/FIGHT/REVENGE` track reciprocal consent and outcomes. Test crossed requests, distance/map changes, logout, death and stale pair cleanup. |
| SRV-027/SRV-024 | Arena and guild-war observers | `CArenaManager`, `CWarMap` and the player `observer_exit` command maintain spectator membership/counts and exclude observers from party/trade/item/combat paths. Spectator visibility and exit/restore location need explicit authority and privacy rules. |
| SRV-022 | Player block preferences | `CHARACTER::SetBlockMode` persists separate flags for exchange, party invite, guild invite, whisper, messenger invite and party request; target handlers enforce them. Preserve all six toggles and distinguish them from sanctions. |
| SRV-022/SRV-051 | Chat block/mute and vote-block moderation | `AFFECT_BLOCK_CHAT`, `block_chat`, `block_chat_list` and `vote_block_chat` implement timed moderation across cores. Rebuild this as permissioned sanctions with actor/reason/expiry/appeal evidence rather than conflating it with a player's whisper block. |
| SRV-022/SRV-034 | Emotes and mutual emote permission | `cmd_info` exposes kiss, slap, French kiss, clap, cheers, dances and expressive emotes; `emotion_allow` and `do_emotion` handle paired consent. Motion/effect availability and restrictions need generated action IDs and two-client tests. |

### Item-use, mobility and character-identity flows

| Parent ID | Named subfeature | Execution evidence and planning obligation |
| --- | --- | --- |
| SRV-013/SRV-014 | Equip/unequip families | `CHARACTER::UseItemEx` dispatches weapon, armour, costume, rod, pick, ring, belt, unique and special Dragon Soul equipment, while normal Dragon Soul placement uses item movement. Validate job/sex/level/anti-flags, wear-slot conflicts, polymorph, exchange locks, expiry and derived affects. |
| SRV-010/SRV-013 | Recovery, ability, cleansing and invisibility consumables | Live `ITEM_USE` branches cover delayed, immediate and continuous HP/SP recovery, ability buffs, direct affects, bad-affect clearing and invisibility. Arena/dungeon/war limits and use/consumption ordering are part of the rules. |
| SRV-013/SRV-015 | Refinement scrolls, Metin stones, sockets and attributes | Live branches cover tuning/detachment, socket cleaning, normal/rare attribute add/change, accessory socket creation/insertion, belt sockets and Metin insertion. Keep target validation, probability, failure result, item consumption and logs transactional; source enum coverage alone does not select every scroll variant. |
| SRV-006/SRV-013 | Return, memory and destination warp items | `USE_TALISMAN` handles return-to-town and saved-location items with dungeon/health/cooldown restrictions. Selected [`ring_warp.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/ring_warp.quest) adds an item with destination menu, charge count and cooldown. Warp validation and charge consumption must be one recoverable transition. |
| SRV-006/SRV-029 | NPC/map warp services | Selected `map_warp.quest`, `neutral_warp.quest` and `goto_empire_castle.quest` provide destination/empire transport separately from warp items. Compile destinations against the map profile, bounds, access rules and fees. |
| SRV-012/SRV-013 | Gift boxes, keyed treasure boxes and special-item groups | `ITEM_GIFTBOX` and `ITEM_TREASURE_KEY` resolve `CSpecialItemGroup` results including item, gold, EXP, mob/group and negative effects. Reward roll, capacity, consumption and spawned outcomes must commit exactly once; direct use of `ITEM_TREASURE_BOX` returns false. |
| SRV-013/SRV-028 | Quest and signal-use items | `ITEM_QUEST` routes through `CQuestManager::UseItem` or `SIGUse` according to flags/group IDs; many selected quests also bind exact item-vnum `use`. Content compilation must reconcile both dispatch routes and reject duplicate reward/consumption paths. |
| SRV-039-SRV-043 | Fish, bait, rod, pick, campfire, polymorph and cube interactions | `UseItemEx` has concrete fish/bait/rod, pick, campfire and polymorph branches; `fishing`, `mining` and cube handlers own their action/RNG/cost flows. Each needs map/tool/state checks and durable item outcomes. |
| SRV-017 | Private-shop bundle | Item 50200 invokes `__OpenPrivateShop`/`UseSilkBotary`; normal command rows close shops. Reserve stock and settle purchases through the authoritative shop transaction rather than treating the bundle as a cosmetic opener. |
| SRV-044/SRV-045 | Dragon Soul extraction/decks, blend, hair and costume utilities | `ITEM_DS`, `ITEM_SPECIAL_DS`, `ITEM_EXTRACT`, `ITEM_BLEND` and `ITEM_HAIR` have live handlers, but belong to later-feature profiles unless the chosen baseline includes them. |
| SRV-013 | Defined but non-executing item categories | `ITEM_AUTOUSE`, `ITEM_MATERIAL`, `ITEM_SPECIAL`, `ITEM_TOOL` and `ITEM_LOTTERY` reach an empty `UseItemEx` branch at this pin; `USE_MOVE`, `USE_TREASURE_BOX` and `USE_MONEYBAG` also do no direct work there. Keep them in compatibility/import reports, but do not claim live standalone features without another handler or selected quest. |
| SRV-003 | Character name change | Selected [`change_name.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/change_name.quest) checks marriage, polymorph, guild, party, level, cooldown and name availability, consumes item 71055 and requires relog. Its internal quest name is misspelled `chagne_name`, so runtime parity is unverified; redesign references around stable character IDs. |
| SRV-003/SRV-034 | Character sex change | Selected `item_change_sex.quest` checks level, engagement/marriage, polymorph and cooldown, consumes item 71048 and calls `pc.change_sex`. Decide what happens to equipped items, appearance assets and class restrictions transactionally. |
| SRV-003/SRV-023/SRV-034/SRV-047 | Empire change | Selected [`change_empire.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/change_empire.quest) blocks engagement/marriage, polymorph and guild membership, checks gold/item/cooldown, then calls `pc.change_empire`. Reconcile all empire-keyed character, spawn, language, guild, friend and quest state atomically. |

### Selected quest/content families that remain separate deliverables

| Parent IDs | Named selected material | Coverage consequence |
| --- | --- | --- |
| SRV-007/SRV-028 | Starter equipment, `levelup`, main route level 1-98 and flame route 99-105 | Baseline and high-level routes must be split by profile; validate every level/kill/item/NPC gate and reward branch. |
| SRV-028/SRV-029 | Side quests, quest-scroll bands and collection/biologist lines level 4-94 | Collection timers, repeated turn-ins, random acceptance and final permanent bonuses require durable per-character state and deterministic fixtures. |
| SRV-016/SRV-019/SRV-020 | Blacksmith/fishrod shops, mall/warehouse, gold bars, premium/voucher cash and shop-box quests | Each currency/storage/external-award boundary needs separate authorization, cap, provenance and failure recovery. |
| SRV-023-SRV-025 | Guild create/manage/master transfer/ranking, building/altar/melt/NPC and war join/bet/observer | Creation fees/cooldowns, 15 grades and four permission bits, member contribution, treasury, skills, land and each war/bet state are individually testable. |
| SRV-030-SRV-033 | Devil Tower, catacomb, spider floors, Heaven's Cave/Blue Dragon/Dragon Lair and Flame Dungeon | These are separate access, instance, encounter, timer and reward graphs; source presence does not prove a complete selected pack. |
| SRV-046-SRV-049 | Empire privileges, Three-Way War, arena/OX, Christmas, Easter, Ramadan, Halloween, Valentine, harvest and mystery-box events | Every event has independent schedule/flag/content/reward/recovery needs. Some seasonal ride/costume items also depend on later-system profiles. |
| SRV-034-SRV-036 | Couple-ring acquisition, proposal/engagement, dress and fee checks, ceremony conversion/gifts, guest list/join, music/dark/snow, partner proximity/love points, ring/bonus cleanup, mutual and unilateral divorce | Selected `couple_ring.quest` and [`marriage_manage.quest`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/gamefiles/data/quest/marriage_manage.quest), native `marriage` APIs, `TMarriage::NearCheck` and `WeddingMap` establish these as distinct scenario branches. |
| SRV-013/SRV-028/SRV-050 | Item informer/delete utilities, localized dialogue, quest letters/targets/counters/clocks and test-server notices | These are supporting player-facing workflows, not generic quest-engine completion. Their UI, localization and authorization must be covered or explicitly excluded. |

## Compile-time and content-dependent variants

The actual service switch file has only two product switches:
[`service.h`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/common/service.h)
defines `__PET_SYSTEM__` and comments out `__AUCTION__`. The auction macro still
guards 36 occurrences across game, DB, shared tables and commands. Auction must
be recorded as available source, disabled baseline behavior.

`__FISHING_MAIN__` and `__MATRIX_MAIN_ENABLE__` are commented standalone-test
harness switches; undefined means the normal game implementation is compiled.
`M2_USE_POOL`, `USE_STACKTRACE` and `__UNITTEST__` are also undefined in the
baseline. The ledger records every occurrence and definition site rather than
guessing from filenames.

Runtime flags and content are equally important. `test_server`, `auth_server`,
channel/map allowlists, locale selection and quest event flags change behavior.
Quests can activate drops, arenas, Christmas/Easter/Ramadan/Halloween systems,
guild delays, privilege bonuses, three-way war, OX state and dungeon access.
Consequently, a feature is complete only when code, selected definitions,
quest/event configuration, map content, client presentation and tests all agree.

Use explicit build/content profiles:

1. `classic-baseline`: the chosen historical release and exact balance/data
   manifest. Horse, core quests/social/economy remain here only when evidenced by
   that release.
2. `later-official`: individually versioned additions such as Dragon Soul,
   costume/belt/energy, pets, high-level maps and quest lines.
3. `experimental`: disabled or incomplete source such as auction and Speed
   Server. It cannot leak into compatibility claims.

Profiles should select data and schema-compatible capabilities, not C++-style
preprocessor forks scattered across runtime logic.

## Quest and server-content inventory

The bundled quest tree contains 284 `.quest` sources. `locale_list` selects 238;
the remainder includes tests, prototypes, backups, `xxx_` legacy material and
inactive variants. Major selected families include the level 1-105 main route,
subquests, collection/biologist quests, horse progression, guild creation and
management, guild war/betting/observer flows, marriage and couple ring, shops,
blacksmith/refining, mining/fishing, empire change, dungeons, Dragon Soul,
energy/pets/mounts and seasonal events. The exact selected and unselected names
are in the tracked ledger; file count is not proof that a quest compiles,
terminates, grants valid rewards or belongs to the chosen release.

The native Lua registry is substantial: 27 namespaces and 532 parsed binding
names. Counts are: `pc` 170, global 67, dungeon `d` 60, `item` 26, `npc` 23,
`horse` 20, `guild` and `party` 17 each, quest `q` 16, `forked` and monarch `oh`
15 each, `marriage` 15, `affect` 11, `game` 10, `oxevent` 8, `speedserver` and
`target` 7 each, arena/pet 5 each, building 5, Dragon Soul 3, plus battle arena,
dance event, Dragon Lair, management, member and mob tables. Registration is in
[`questlua.cpp`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/questlua.cpp);
the ledger maps every exposed name to its binding symbol and source file.

The API can grant items/gold/EXP, mutate levels/stats/skills/quest flags, warp or
kill players, spawn/purge mobs, change privileges, manage guilds/parties/marriage,
create dungeons, schedule timers and issue raw client/GM commands. This power is
the main reason to avoid shipping an unrestricted legacy Lua runtime. A modern
quest platform needs capability-scoped APIs, validated IDs/ranges, instruction
and timer budgets, transactional rewards, versioned state migrations, static
validation, structured logs, deterministic test clocks/RNG and an owner-only
publish workflow. Player exports must contain no authoring evaluator or secret.

The server data snapshot includes:

- 112 map directories and 680 map files. Common files are `Setting.txt`,
  `Town.txt`, `server_attr`, `regen.txt`, `npc.txt`, `boss.txt` and `stone.txt`,
  plus specialized dungeon/portal records. It covers empire starters, second
  maps, guild villages/lands, deserts, snow, flame, orc/temple/forest, monkey and
  spider dungeons, Devil Tower/catacomb, Dragon Lair, wedding, OX, PvP/battle
  arenas, empire war/sungzi, siege, test and later maps.
- 293 monster motion directories, 4,781 motion/metadata files, 662 male-PC and
  650 female-PC motion files. These matter to the server because
  `CMotion::LoadMobSkillFromFile` reads duration, accumulation and hit-sphere
  events. They must join the automated model/animation conversion pipeline.
- `item_proto.txt` with 5,744 lines and `mob_proto.txt` with 1,335 lines,
  including headers; 15 localized item-name files and 15 mob-name files.
- Large rule catalogs: `mob_drop_item.txt` 7,792 lines,
  `special_item_group.txt` 11,409, `group.txt` 6,613,
  `group_group.txt` 1,803, `cube.txt` 1,091, `common_drop_item.txt` 540,
  `dragon_soul_table.txt` 314, `fishing.txt` 42 and `skill_power.txt` 79.
  `drop_item_group.txt` is empty at this pin.
- Dungeon/easter/mob-spawn support directories and 15 locale-string/translation
  sets. Translation Lua files are very large generated-looking catalogs and
  should be normalized rather than manually maintained.

At boot, [`CClientManager::InitializeTables`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/db/src/ClientManagerBoot.cpp)
loads/mirrors mob and item proto, then loads SQL-backed shops, skills, refining,
normal/rare item attributes, banwords, lands, object prototypes/instances and
monarch state. The game receives those tables through a version-6 raw boot
packet in `CInputDB::Boot`. Additional flat files feed groups, drops, fishing,
cube, Dragon Soul, motion metadata, maps, regens, locales and quests.

There is no SQL schema or migration set in this repository. Query strings imply
account, player/player_index, item, quest, affect, safebox, guild/member/grade,
guild wars/reservations/bets, messenger, marriage, monarch, land/object,
myshop-pricelist, awards and log domains, but a real source database was not
available for schema/constraint verification. A standalone content build is
also incomplete: the empty drop-group file, SQL-only definition tables and
missing client-side assets prevent treating this checkout as a runnable truth
set.

## Rebuild contracts

Every vertical slice should define these contracts together:

| Contract | Required behavior |
| --- | --- |
| Identity and session | Account owns character; one controlling connection per policy; reconnect resumes valid state; disconnect removes presence without deleting durable state. |
| Intent and validation | Client submits bounded intent and sequence/idempotency key. Server checks identity, phase, map/instance, ownership, finite/ranged numbers, distance, cooldown, resources and permissions. |
| Transaction | Item, currency, relationship, guild, trade, quest reward and auction-like changes commit atomically or not at all. No client animation or cached row is evidence of success. |
| Visibility | Public map state, party/guild state and private inventory/quest/account state use intentional subscriptions/RLS; hidden and offline fields are not broadly readable. |
| Time and recovery | Cooldowns, effects, respawns, event schedules, dungeons, weddings and wars use durable deadlines/state machines with idempotent recovery after reconnect/restart. |
| Content compatibility | Client/server share definition IDs, coordinate transform, source hashes, compiler version and profile/content hash before entry. |
| Evidence | Reducer rejection, duplicate/replay, two independent clients, remote updates, disconnect, reconnect and restart are tested for each changed path. |

For multi-map growth, add explicit `map_id`, `instance_id`, entry phase and
spawn/exit records before dungeons or wedding maps. A portal transaction checks
access and commits membership/position, while the client loads matching content
and switches subscriptions. A timeout or reconnect must resolve to exactly one
valid location. Parties, guilds, marriage and event membership cannot be stored
only in a process-local manager.

## Automated authoring and import

Repeated work should use one content compiler, analogous to the existing map/UI
pipelines. Inputs remain ignored, pinned and rights-separated; normalized source
manifests and project-authored corrections are versioned. The pipeline should:

1. Discover explicit pinned inputs without recursive "import everything"
   behavior. Record upstream commit/blob, SHA-256, source profile and rights.
2. Parse item/mob proto and localized names; skills/formulas; refine and item
   attribute tables; shops; drops/groups; fishing/cube/Dragon Soul; maps,
   server attributes, towns, NPC/boss/stone/regen/portals; dungeons; motion data;
   and selected quests/event configuration.
3. Normalize coordinates, IDs, enums, money/probability/time units and locale
   keys into typed intermediate records. Apply explicit, reviewable overrides.
4. Validate uniqueness and foreign keys; enum/range/cap constraints; map bounds
   and walkability; spawn radii/counts/timers; drop/craft/refine probabilities;
   upgrade cycles; shop prices/currencies; quest trigger/function availability;
   reward validity; localization placeholders; motion clips/events; and
   client/server asset references.
5. Emit server definitions/seed migrations, Godot resources, animation/hit
   metadata, generated bindings, test fixtures and a shared content manifest.
   Outputs are deterministic and never hand-edited.
6. Produce human-readable diagnostics, summary counts, unused/missing-reference
   reports, semantic diffs and approval-ready release bundles. CI rebuilds twice
   and checks byte identity, then runs representative server and rendered-client
   tests.

Quest publishing should compile against an allowlisted API schema and the same
definition manifest. It should reject unknown NPC/item/map/quest IDs, unreachable
states where detectable, unbounded reward/timer arguments and calls unavailable
in the selected profile. Use small fixture quests to test login, level, kill,
click, item use/take, timer, party, guild, marriage and dungeon triggers before
accepting a full catalog.

The animation pipeline must not stop at rendering. For each PC/mob motion it
should pair model/skeleton/clip conversion with canonical motion mode, duration,
root displacement, hit/skill event spheres, server range/timing and a visual
test scene. Missing animations or server event records should fail the selected
profile unless an explicit fallback is declared.

## Development, GM and live-operations tooling

[`cmd_info`](https://git.old-metin2.com/metin2/server/src/commit/7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318/src/game/src/cmd.cpp)
contains 233 parsed rows, of which 218 compile on pinned master and 15 are inside
the disabled `__AUCTION__` branch. Across all lexical rows there are 98
player-level, 66 low-wizard, 41 high-wizard, 23 implementor, three god and two
wizard rows. It includes normal logout/restart,
party/PvP/horse/cube/Dragon Soul operations alongside teleport, spawn/item/stat/
skill grants, player disconnect/kill, quest flag/state edits, reload, event
flags, notices, moderation, guild-war, land, arena, monarch/election and shutdown
controls. `gamefiles/conf/CMD` can override privilege levels at runtime.

Do not reproduce a privileged text-command interpreter as the primary admin
surface. Build authenticated tools with narrowly scoped roles, structured input
validation, preview/dry-run for bulk operations, reason/ticket fields,
idempotency keys and an immutable audit trail. Needed surfaces include:

- Player/account/character lookup, presence/session inspection, disconnect/ban/
  mute, safe relocation, inventory/currency/quest inspection and exceptional
  recovery grants with before/after records.
- Content-definition lookup, active profile/hash, spawn/map/instance overlays,
  validation errors, staged publish/rollback and live reload only for explicitly
  reload-safe definitions.
- Event calendar, flags, start/stop/status, OX questions, spawn waves,
  announcements and reward previews. Event transitions survive operator retries
  and server restarts.
- Party/guild/war/land/marriage/wedding/monarch state inspection and constrained
  repair operations. Repairs invoke normal invariants and reconcile all related
  rows.
- Economy dashboards for sources/sinks, trades/shops/refines/drops/grants,
  suspicious duplication, rate-limit/rejection metrics, reducer latency,
  subscription volume and instance/entity counts.
- Local developer fixtures to create disposable accounts/characters, seed a
  tiny representative content pack, control test clock/RNG, simulate latency/
  reconnect and launch two independent clients. Developer powers remain local
  and are excluded from release builds.

Production operations need migrations, cold and logical backups, restore drills,
content/profile rollback, compatible-client policy, secret rotation, moderation
retention and incident logs. A successful import or linter run is not gameplay
evidence; the actual exported client and intended endpoint must exercise each
milestone.

## Decisions that must precede a completeness claim

1. Select an exact classic reference release/region. Freeze its jobs, level cap,
   maps, systems, item/mob/skill tables, quests, rates and known quirks.
2. Decide which quirks are presentation/balance compatibility and which are
   security, data-loss or exploit bugs that will be fixed. Document changed
   outcomes explicitly.
3. Assign each later or conditional family to baseline, later-official,
   experimental or excluded. At minimum decide pets, auction, Speed Server,
   Dragon Soul, costume/belt/energy, high-level maps, monarch and each event.
4. Obtain/licence the necessary source data and assets independently. This
   inspection supplies no redistribution permission.
5. Turn the tracked machine ledger into coverage checks: every command/API/
   packet/content category is mapped to a replacement, an intentional exclusion
   with rationale, or a still-open milestone. This prevents visually impressive
   slices from silently omitting marriage, elections, land, event recovery,
   authoring or administration.

The audit establishes breadth and dependencies from one pinned historical
source. It does not establish a clean build, database compatibility, quest
compilation, runtime behavior, client/server packet agreement, exploit safety,
asset completeness, balance fidelity or current-live-version coverage.
