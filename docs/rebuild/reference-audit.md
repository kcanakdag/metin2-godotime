# Emulator and live-feature reference audit

This audit covers two independently implemented server emulators and the
Gameforge-domain, community-maintained English Metin2 wiki. It is a static
source review performed on 2026-09-06. No downloaded code was installed,
executed, or copied into the game. The results describe evidence in exact
snapshots; they do not certify
end-to-end behavior with an original client.

## Evidence rules and source snapshots

* **Implemented** means a concrete state transition or handler exists and has at
  least one adjacent test or a complete call path in the inspected tree.
* **Partial** includes scaffolding, protocol/schema constants, unfinished call
  paths, untested implementations, or an implementation with material TODOs.
* **Absent** means no implementation was found in the complete inspected tree,
  not that no implementation exists in another branch or private fork.
* Upstream README roadmap marks are claims. They are recorded as inventory data,
  but they never override code and test evidence.
* The wiki is hosted under Gameforge's domain and describes itself as community
  maintained. Its index supports classifying a named system as live-product
  scope, while the page text is not guaranteed publisher-authored and is not a
  protocol specification or an exact balance contract.

| Reference | Immutable revision | Current-head check | Terms and use |
| --- | --- | --- | --- |
| [open-mt2](https://github.com/willianmarquess/open-mt2/tree/8d8800d470f0b69221886723eb5877a2ed9d9d8d) | `8d8800d470f0b69221886723eb5877a2ed9d9d8d` | Still default-branch HEAD on 2026-09-06 | `LICENSE` is GPL-3.0 while `package.json` says ISC. Treat as GPL-3.0 research material unless reviewed otherwise. Original game data and assets have separate rights. |
| [Quantum Core X](https://github.com/MeikelLP/quantum-core-x/tree/ddab58ba493dfcedefd8b265513950f865edfffc) | `ddab58ba493dfcedefd8b265513950f865edfffc` | Default-branch HEAD on 2026-09-06 | MPL-2.0. The repository says it is a non-backward-compatible fork of an older QuantumCore project. MPL terms do not grant rights to Metin2 data or assets. |

The ignored snapshots are under `.cache/full-game-research/emulators/`. Their
archive hashes, tree counts, and wiki-page revision IDs are recorded in
`docs/rebuild/evidence/reference-inventory.json`.

## System-level implementation matrix

The status is deliberately conservative. “Partial” often still means valuable
reference code, especially for invariants and failure cases.

| System | open-mt2 | Quantum Core X | Evidence and gap |
| --- | --- | --- | --- |
| Account, login, character lifecycle | Implemented | Implemented | open-mt2 has auth/game services and packet tests, including logout and return-to-select cleanup. QCX has token login and select/create/delete handlers, but IP verification remains a TODO in `TokenLoginHandler`. |
| Server-authoritative movement | Implemented | Partial | open-mt2 `CharacterMoveService.execute` calls `Player.isMoveAllowed`, whose distance/rate budget rejects and resynchronizes; tests cover move types and teleport-rate checks. QCX `CharacterMoveHandler.ExecuteAsync` changes entity position, while `Entity.Move` still says “Verify position possibility”. |
| World, maps, interest management | Implemented | Implemented | open-mt2 `Area`/`EntityManager` use map attributes and nearby-entity lifecycle tests. QCX `Map.Update` maintains a quadtree and symmetric nearby sets; `World.LoadAsync` maps atlas regions and remote hosts. |
| Mob/stone spawn and behavior | Implemented | Implemented, with TODOs | open-mt2 has `SpawnManager`, monster/stone behavior and map-attribute-aware tests. QCX has `SpawnPointProvider`, `Map.SpawnGroup`, `SimpleBehaviour`, and `StoneBehaviour`; targeting and attack-speed details remain TODOs. |
| Physical/ranged/magic combat | Partial | Partial | open-mt2 `PlayerBattleAgainstMobStrategy` has distance, weapon, defense, critical, piercing, resistance and timed-effect paths with extensive tests; its roadmap still marks attack/defense in progress and PvP completeness is not established. QCX `Entity.Attack` implements melee/range basics but omits range validation, magic attack, many bonuses/resists, block/reflect/steal, and throws for unsupported damage types. |
| Class and horse skills | Partial but broad | Partial | open-mt2 `SkillManager.load` has 55 explicit entries: 48 active and 7 passive. Two additional horse passive classes are wired outside that registry. `PlayerSkill` has costs, cooldowns, books, ranks, splash/chain and toggles, alongside explicit TODOs. QCX `PlayerSkills` covers assignment, persistence and skill learning, while combat effects remain materially incomplete. Neither registry has Lycan skills. |
| Stats, equipment applies, affects, regeneration | Partial | Partial | open-mt2 `PlayerPoints`, `PlayerApplies`, player recovery and effect tests cover many classic point types. Some affect-dependent paths remain TODO. QCX derives several points/equipment effects, but its combat TODO inventory shows major missing consumers. |
| Inventory, equipment, item use | Implemented classic core; modern slots partial | Implemented classic core; modern slots partial | Both have grid inventory, equipment placement, persistence and validation. Both support body/hair costume slots. open-mt2 also declares belt and Dragon Soul windows/types, but no belt-storage or alchemy workflow was found; constants are not system evidence. |
| Ground items and drops | Partial | Partial | open-mt2 has ownership expiry, pickup-distance, stacking and configurable drop tests; premiums/party/guild/marriage bonuses remain TODO. QCX `DropProvider` covers several legacy drop files, while sockets, rates and some grouped formats remain TODO. |
| NPC shops | Implemented | Implemented | open-mt2 `ShopService` tests open/buy/sell failure paths. QCX `World.LoadShops`, `Shop`, and JSON/TSV providers register NPC-click shops. |
| Player private shops | Implemented online shop only | Absent | open-mt2 `PrivateShopService` validates listings, locks item instances, checks distance/currency/overflow, transfers atomically with rollback, and has detailed tests. It has no offline persistence/search/Won system. QCX `Shop` explicitly says player shops still need implementation. |
| Quests | Partial | Scaffold/partial | open-mt2 has decorator-based event/state registration, 11 concrete quest classes, answer/logout/kill tests, and unfinished persistence/reward paths. QCX discovers attributed quests, but `QuestManager.InitializePlayer` has `todo load state` and only internal/test/level-up examples. |
| Horse, mount, polymorph | Implemented horse slice; broader mounts absent | Absent | open-mt2 has `PlayerHorse`, horse stats, quests, commands, mount/dismount/death and persistence tests, plus polymorph item/command paths. QCX has no horse or mount subsystem in the inspected tree. |
| Chat/shout/whisper | Talk and shout only | Talk, shout, notice, whisper | open-mt2 `ChatService` handles nearby talk and empire shout with rate/cooldown tests, but no whisper implementation was found. QCX `ChatManager` broadcasts across cores through Redis and `WhisperHandler` sends direct messages; empire handling is still hard-coded in two paths. |
| Commands and privileged administration | Partial and unsafe as shipped | Broad, with permission caveat | open-mt2 has 31 command directories, validators, and tests, while its README states any player can execute any command. QCX discovers commands and checks permission groups, but several gameplay commands and `ReloadPermissionsCommand` use `CommandNoPermission`; adopt an explicit server-side authorization policy rather than copying annotations. |
| Guild | Absent | Partial | QCX `GuildManager` and 9 guild packet handlers cover create/member/rank/news/EXP operations, with TODOs for invitation tracking, rejection and fan-out. open-mt2 has guild-related constants/data files but no guild domain or handlers. |
| Party/group play | Absent | Absent | Neither inspected tree has player party membership, invite, leader, loot, EXP-distribution, or party-skill behavior. QCX `GroupCommand` concerns mob spawn groups. |
| Direct player trade | Absent | Absent | No transactional player-to-player exchange flow was found. Item-give/drop packets in QCX are not a two-party trade contract. |
| PvP duel/ranking/alignment | Absent | Partial primitives only | open-mt2 labels duel TODO. QCX exposes PvP mode/alignment types but no complete duel or war flow. Combat code alone does not establish PvP rules. |
| Fishing and mining | Absent gameplay | Absent gameplay | open-mt2 has item enums and a passive `MiningSkill`, but `PlayerSkill.useSkill` still has a mining-validation TODO and no gathering loop. Neither has fishing gameplay. |
| Refinement, crafting, sockets, bonuses | Absent workflow | Absent workflow | Item proto fields exist, but no complete refine/craft transaction is present. QCX shop creation explicitly omits bonuses/sockets. |
| Dungeons, raids and live events | Absent orchestration | Absent orchestration | Map filenames and spawn data do not implement entry limits, instance ownership, scripted objectives, reset, rewards or reconnect behavior. |
| Persistence and multi-process lifecycle | MySQL/Redis, partial flush/reconnect evidence | EF persistence/Redis multicore, partial | open-mt2 has repositories, migrations, cache and flush/logout tests. QCX has EF migrations, Redis map/session/chat coordination and `RemoteMap`, whose members are still partly `NotImplementedException`. SpacetimeDB should replace these process-oriented patterns with tables/reducers and scheduled work. |
| Legacy client protocol/encryption | Many packets; encryption absent | Many packets; XTEA and generated serializers | open-mt2 has 31 inbound handlers, 26 validators and 53 outbound packet files; its roadmap marks encryption TODO. QCX has 91 API packet files and 38 handler files plus Roslyn serialization generation. These are references only because the Godot client uses the SpacetimeDB protocol. |
| Automated verification | Strong unit-level evidence | Useful but smaller suite | Static count: open-mt2 has 143 unit test files and 973 `it(...)` cases; QCX has 24 test files containing 215 `[Fact]`/`[Theory]` cases. Neither count proves original-client or production correctness. |

The matrix is grounded in these immutable implementation, registry and test
anchors. Paths not listed here remain inventoried in
`docs/rebuild/evidence/reference-inventory.json` and the ignored REF catalog.

| Reference | Immutable path and symbol | Evidence use |
| --- | --- | --- |
| open-mt2 movement | [`src/game/app/service/CharacterMoveService.ts` — `CharacterMoveService.execute`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/game/app/service/CharacterMoveService.ts); [`Player.ts` — `Player.isMoveAllowed`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/entities/game/player/Player.ts); [`CharacterMoveService.test.ts`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/game/app/service/CharacterMoveService.test.ts) | Validation, rejection and resync call path plus service tests. |
| open-mt2 combat | [`PlayerBattleAgainstMobStrategy.ts` — `execute`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/entities/game/player/delegate/battle/PlayerBattleAgainstMobStrategy.ts); [`PlayerBattleAgainstMobStrategy.test.ts`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/core/domain/entities/game/player/delegate/battle/PlayerBattleAgainstMobStrategy.test.ts) | Concrete formula and failure-case coverage; unresolved TODOs keep the overall status partial. |
| open-mt2 skills | [`SkillManager.ts` — `SkillManager.load`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/manager/SkillManager.ts); [`PlayerSkills.test.ts`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/core/domain/entities/game/player/delegate/PlayerSkills.test.ts) | Auditable registry cardinality and skill-use/learning coverage. |
| open-mt2 inventory and private shop | [`PrivateShopService.ts` — `openPrivateShop/buy`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/game/app/service/PrivateShopService.ts); [`PrivateShopService.test.ts`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/game/app/service/PrivateShopService.test.ts); [`Inventory.test.ts`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/core/domain/inventory/Inventory.test.ts) | Exact-item locking, capacity, overflow and rollback evidence for the connected-owner shop. |
| open-mt2 quests and horse | [`QuestManager.ts` — `load/registerTask`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/quests/QuestManager.ts); [`QuestManager.test.ts`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/core/domain/quests/QuestManager.test.ts); [`PlayerHorse.ts`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/src/core/domain/entities/game/player/delegate/PlayerHorse.ts); [`PlayerHorse.test.ts`](https://github.com/willianmarquess/open-mt2/blob/8d8800d470f0b69221886723eb5877a2ed9d9d8d/test/unit/core/domain/entities/game/player/PlayerHorse.test.ts) | Quest event/state scaffold and the stronger horse vertical slice. |
| QCX movement and AOI | [`CharacterMoveHandler.cs` — `ExecuteAsync`](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/PacketHandlers/Game/CharacterMoveHandler.cs); [`Map.cs` — `Map.Update`](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/World/Map.cs); [`MapTests.cs`](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Tests/Core.Tests/MapTests.cs) | Movement mutation is partial; quadtree and nearby-set maintenance have direct tests. |
| QCX combat and guild | [`Entity.cs` — `Attack/Damage`](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/World/Entities/Entity.cs); [`GuildManager.cs`](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/GuildManager.cs) | Concrete partial paths whose TODOs expose missing validation, damage channels and guild invitation/fan-out behavior. |
| QCX quests and commands | [`QuestManager.cs` — `InitializePlayer`](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Server/Quest/QuestManager.cs); [`CommandManager.cs` — `Register/CanUseCommand`](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Libraries/Game.Commands/CommandManager.cs); [`StrictCommandManagerTests.cs`](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Tests/Game.Commands.Tests/StrictCommandManagerTests.cs) | Reflection discovery and permission structure are reusable ideas; quest state loading remains a TODO. |
| QCX generators and operations | [`PacketSerializerGenerator.cs`](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Core.Networking.Generators/PacketSerializerGenerator.cs); [`DocsGenerator/Program.cs`](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Executables/DocsGenerator/Program.cs); [`WorldUpdateBenchmark.cs`](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Game.Benchmarks/Benchmarks/WorldUpdateBenchmark.cs); [`GameTickListener.cs`](https://github.com/MeikelLP/quantum-core-x/blob/ddab58ba493dfcedefd8b265513950f865edfffc/src/Plugins/PrometheusPlugin/GameTickListener.cs) | Typed generation, generated catalogs, benchmarking and observability seams. The tick histogram is declared but never observed. |

## Live-product extension gap

The classic emulator trees are a starting point, not the current product scope.
The links below use fixed MediaWiki `oldid` revisions where available. They are
pages from a Gameforge-domain wiki whose own main page says it is community
maintained, so they establish a live-product inventory but are not guaranteed
publisher-authored technical rules. “Absent” means absent from both emulator
implementations unless the note says partial.

At Main Page revision 61798, the transcluded EquipmentAndOthersV2 template
revision 57872 contains exactly 17 entries under **Systems**. Sixteen destinations
resolve and `Merc System` is a red link. The transcluded World MapV2 template
revision 61395 contains 86 named destination links in 11 groups. Exact link
targets, display aliases, group counts, and missing destinations are stored in
`docs/rebuild/evidence/reference-inventory.json`; indexing a destination does not
establish its entry rules, map geometry, spawns, or dungeon state machine.

| Live system | Gameforge-domain wiki evidence | Emulator result and planning consequence |
| --- | --- | --- |
| Lycan class | [Lycan, revision 48334](https://en-wiki.metin2.gameforge.com/index.php?title=Lycan&oldid=48334) lists the Instinct skill set | Absent. Both class registries stop at Warrior, Ninja, Sura and Shaman. Treat Lycan as a post-classic expansion slice with job creation, claw equipment, animation, skill, balance and UI dependencies. |
| Belt system | [Belt System, revision 58127](https://en-wiki.metin2.gameforge.com/index.php?title=Belt_System&oldid=58127) describes equipment, refinement, sockets and conditional storage | open-mt2 declares belt types/slots/windows but has no storage/refinement workflow; QCX lacks belt types. Implement as a server-owned container whose capacity depends on the equipped belt, with atomic unequip rules. |
| Costume and transmutation | [Costume System, revision 58122](https://en-wiki.metin2.gameforge.com/index.php?title=Costume_System&oldid=58122) confirms body, hair and weapon skins, timed items, bonuses and transmutation | Basic body/hair equipping is partial in both emulators. Weapon skins, timed expiry, bonus rerolls/transfers, set bonuses and transmutation are absent. Separate appearance projection from stat-bearing item state. |
| Aura Outfit system | [Aura Outfit System, revision 60698](https://en-wiki.metin2.gameforge.com/index.php?title=Aura_Outfit_System&oldid=60698) describes a visible costume slot, accessory absorption, 250 levels, six stages and evolution | Absent. It depends on appearance, equipment-instance destruction/absorption, deterministic bonus projection, EXP and stage tables. Keep absorbed source data and the projected effective bonus auditable. |
| Shoulder sash | [Shoulder Sash System, revision 60665](https://en-wiki.metin2.gameforge.com/index.php?title=Shoulder_Sash_System&oldid=60665) confirms four grades, destructive combination and bonus absorption/transfer | Absent. Needs irreversible-operation previews, exact input-instance locking, outcome tables, and appearance/stat projection. |
| Binding system | [Binding System, revision 60675](https://en-wiki.metin2.gameforge.com/index.php?title=Binding_System&oldid=60675) describes soulbound equipment restrictions and a 72-hour unbinding transition | Absent. Binding must be enforced by every drop, trade, sell, refine, enchant and character-delete reducer. Store the unbind deadline durably and make cancellation/immediate-unbind transitions explicit. |
| Pet system | [Pet System, revision 61698](https://en-wiki.metin2.gameforge.com/index.php?title=Pet_System&oldid=61698) confirms hatch, lifetime, feeding, EXP, evolution, randomized type and skills | Absent. Model pet identity and time independently of its seal item; schedule expiry on authoritative time and test logout/reconnect. This differs from simple cosmetic follower pets. |
| Monster Card system | [Monster Card System, revision 47611](https://en-wiki.metin2.gameforge.com/index.php?title=Monster_Card_System&oldid=47611) describes rotating kill missions, per-monster collection levels, account-wide achievements, transformation and teleport unlocks | Absent. It needs account-scoped collection state, server-selected mission targets, reset limits, polymorph integration, content-location lookup and entitlement policy. The page itself says the level-five summon was still in development, so do not infer a completed summon contract. |
| Merc system | [Main Page, revision 61798](https://en-wiki.metin2.gameforge.com/index.php?title=Main_Page&oldid=61798) includes `Merc System` among the 17 system links, but the destination is missing; [User Interface, revision 61696](https://en-wiki.metin2.gameforge.com/index.php?title=User_Interface&oldid=61696) identifies a Merc UI button | Presence is indexed, detailed rules are unverified, and both emulators are absent. Keep it as a separately gated research slice; reward-chest references alone do not define mission, companion, timing or operation rules. |
| Dragon Stone Alchemy | [Dragon Stone Alchemy, revision 60545](https://en-wiki.metin2.gameforge.com/index.php?title=Dragon_Stone_Alchemy&oldid=60545) confirms a separate inventory, two sets, activation time and three upgrade axes | open-mt2 has enum/window compatibility only; no alchemy. Needs dedicated inventory, refinement transactions, daily quest limits, activation timers and bonus aggregation. |
| Soul Relic system | [Relic System, revision 50531](https://en-wiki.metin2.gameforge.com/index.php?title=Relic_System&oldid=50531) describes class-specific relics, repeatable soul acquisition, irreversible installation, activation time, recharge and up to four proc-like bonuses | Absent. Model the installed relic separately from consumable souls, use authoritative duration, and drive combat/mount/drop triggers from one effect engine with cooldown state. |
| Energy system | [Energy System, revision 60423](https://en-wiki.metin2.gameforge.com/index.php?title=Energy_System&oldid=60423) confirms item destruction, fragment/crystal production and a timed equipment-bonus multiplier | open-mt2 wires `ENERGY` point constants but has no production/timer system; QCX lacks it. Preserve its cross-cutting bonus dependency in one derived-stat pipeline. |
| Gaya currency and market | [Gaya System, revision 61530](https://en-wiki.metin2.gameforge.com/index.php?title=Gaya_System&oldid=61530) describes a capped currency, probabilistic conversion, per-player rotating market stock, unlockable rows and refresh timers | Absent. Add an explicit currency ledger, validated conversion transaction, deterministic stock generation and authoritative refresh schedule. Never let the client choose its offers or conversion outcome. |
| Mailbox | [Mailbox, revision 61368](https://en-wiki.metin2.gameforge.com/index.php?title=Mailbox&oldid=61368) confirms messages, Yang/Won and one item from level 20 | Absent. Needs durable messages, escrowed attachments, capacity/expiry, fees, identity lookup and atomic claim/idempotency. |
| Offline/premium shop and market search | [Private Shop, revision 61856](https://en-wiki.metin2.gameforge.com/index.php?title=Private_Shop&oldid=61856) confirms Bazaar shops, Yang/Won pricing, tax, offline duration and retained proceeds/items | open-mt2 implements only a connected owner and Yang. QCX player shops are TODO. Persist listings independently of player presence; make buy/claim/close serializable and idempotent. |
| Set Bonus | [Set Bonus, revision 61837](https://en-wiki.metin2.gameforge.com/index.php?title=Set_Bonus&oldid=61837) describes temporary bonuses derived from combinations of timed costumes, skins, pets, mounts and buff items | Absent. Represent each eligible combination as checked content data and recompute on every equipment/timer change; do not persist a bonus that can outlive its required item set. |
| Set Effect | [Set Effect, revision 58178](https://en-wiki.metin2.gameforge.com/index.php?title=Set_Effect&oldid=58178) describes a separate, fallible weapon/armour/helmet transformation with two- and three-piece passive thresholds | Absent. This is distinct from Set Bonus and needs item transformation, catalyst, removal and equipment-set aggregation transactions. Both effects may coexist. |
| Titles | [Titles, revision 60744](https://en-wiki.metin2.gameforge.com/index.php?title=Titles&oldid=60744) describes achievement/event unlocks and one player-visible equipped title | Absent. Store unlock provenance and active selection server-side, validate event/achievement grants, and project only presentation metadata to Godot. |
| Champion levels and Yohara | [Experience, revision 61873](https://en-wiki.metin2.gameforge.com/index.php?title=Experience&oldid=61873) confirms promotion after level 120, Champion EXP and Yohara access | Absent. Treat this as a progression layer with separate EXP/stat rules, content gates and migration policy, rather than extending one level integer casually. |
| Sung Mahi's Will and Yohara encounters | [Sung Mahi Tower, revision 61933](https://en-wiki.metin2.gameforge.com/index.php?title=Sung_Mahi_Tower&oldid=61933) describes four will stats and multi-stage tower rules | Absent. Dependencies include Champion progression, map modifiers, instance orchestration, objective state machines, restrictions, ranking and mailbox rewards. |
| Gloves and Sung Ma stats | [Gloves, revision 56270](https://en-wiki.metin2.gameforge.com/index.php?title=Gloves&oldid=56270) describes a license-gated slot, random base values, Demon Stone sockets and STR/RES/VIT/INT Sung Ma variants | Absent. Add slot-unlock state, class-neutral equipment rules, socket compatibility and four typed Sung Ma stats. Serpent gloves are a later progression family, not proof of a generic glove implementation. |
| Talismans and elemental equipment | [Talismans, revision 61378](https://en-wiki.metin2.gameforge.com/index.php?title=Talismans&oldid=61378) lists elemental talismans and later Will talismans with Sung Ma stats and random element values | Absent. It depends on a dedicated equipment slot, refinement, elemental damage/resistance, item bonuses and Champion/Yohara progression. |
| Precision secondary skill | [Precision, revision 57871](https://en-wiki.metin2.gameforge.com/index.php?title=Precision_(Skill)&oldid=57871) describes a Champion-level passive trained by books that reduces enemy block effectiveness | Absent. Add it to the checked skill registry with progression and combat dependency tests; a UI link or book item is not skill behavior. |
| Serpent equipment progression | [Serpent Design, revision 56642](https://en-wiki.metin2.gameforge.com/index.php?title=Serpent_Design&oldid=56642) identifies class weapon/armour crafting and upgrade materials; [Gloves, revision 56270](https://en-wiki.metin2.gameforge.com/index.php?title=Gloves&oldid=56270) lists level-120 Serpent glove progressions | Absent. This is a content family across crafting, randomized base stats, refinement and class-specific equipment. Keep recipes and upgrade curves in validated data and avoid treating the Serpent Temple map as the system implementation. |
| Elemental offense/resistance | [Bonuses, revision 60352](https://en-wiki.metin2.gameforge.com/index.php?title=Bonuses&oldid=60352) confirms six elements and weapon elemental upgrades | open-mt2 has ice/earth/dark resist points and some damage types, but no complete six-element equipment/upgrade pipeline; QCX explicitly TODOs elemental resist. Centralize typed damage channels and derived resistance caps. |
| Item enchantment and sixth/seventh bonuses | [Bonuses, revision 60352](https://en-wiki.metin2.gameforge.com/index.php?title=Bonuses&oldid=60352) separates intrinsic/default, 1–5 and 6/7 bonuses and describes fallible addition, 24-hour processing, powershards/additives and separate reroll items | Both emulators contain apply/enchantment constants but no complete add/reroll workflow. Store ordered bonus slots and pending operations durably, lock the exact item, consume materials atomically and keep 1–5 rerolls isolated from 6/7 rerolls. |
| Auto-Hunt | [Auto-Hunt, revision 58119](https://en-wiki.metin2.gameforge.com/index.php?title=Auto-Hunt&oldid=58119) describes target filters, range, consumables, skills and resurrection | Absent. It is an optional automation system in the live-product index. If in scope, the server must validate every normal action and entitlement; do not grant a privileged simulation path. |
| “Switchbot” | No matching system was found in the inspected emulator trees or the checked Gameforge-domain wiki pages | **Unverified as an official requirement.** Common private-server usage must be treated as fork-specific policy until an official source is supplied. It must not be folded into “original Metin2” by assumption. |

## Design lessons for the rebuild

The useful behavior is mostly in invariants and state-machine boundaries. Port
those ideas, then express them in Rust reducers and durable SpacetimeDB tables:

* Keep server-owned position and attack validation. open-mt2's reject-and-resync
  movement path and its per-victim attack throttle are concrete abuse cases.
  Reducers should reject non-finite coordinates, cap distance/speed, and emit an
  authoritative correction observable by both clients.
* Make inventory mutations atomic. The online private-shop implementation checks
  the exact listed item instance, currency overflow and buyer capacity, then
  rolls back failed placement. SpacetimeDB transactions are a good fit for these
  invariants; stable item instance IDs remain necessary.
* Use registries as auditable content manifests. open-mt2's explicit skill
  registry and quest event maps make missing coverage visible. Store equivalent
  content IDs and dependencies in checked data, validate uniqueness/references
  at build time, and generate Godot-facing metadata from the same source.
* Replace in-process timers with authoritative timestamps or scheduled reducers.
  Node timers and mutable C# tick objects cannot survive failover by themselves.
  Affects, ownership expiry, pet life, shop duration, quest cooldowns and respawn
  should all resume deterministically after reconnect/restart.
* Make interest management a query/subscription contract. Both emulators show
  symmetric nearby-set maintenance and quadtree filtering; the Godot client must
  subscribe to bounded authoritative rows and prove subscribe/unsubscribe rather
  than treating a database query as a subscription.
* Split deterministic rule calculation from effects and transport. Damage,
  drops, refinement and progression should accept explicit inputs/RNG state and
  return decisions; reducers persist them, while Godot only presents outcomes.
* Preserve the classic feel in movement cadence, animation-derived timing,
  combat formulas, progression and UI flow. TCP packet layouts, MySQL/Redis
  caches, reflection discovery, Node event timers and C# remote-map routing are
  replaceable infrastructure.

For Godot, keep appearance and prediction downstream of authoritative state.
Costume, sash, pet, mount and transmutation systems should project stable server
item/entity IDs into scene resources. Client animation or a locally equipped
mesh is never proof that the corresponding server transaction succeeded.

## Development, authoring and operations lessons

open-mt2 includes focused conversion tools for atlas, map attributes, mob proto,
motion metadata, drops and spawn groups under `tools/`, plus packet-document and
performance scripts. QCX adds a Roslyn `PacketSerializerGenerator`, generated
packet/command documentation, reflection-based command/quest/plugin discovery,
a `WorldUpdateBenchmark`, built-in .NET metrics and a Prometheus plugin. These
are evidence that content and protocol automation deserve first-class scope.

For this project, prefer checked schemas and generators that emit both server
validation data and Godot resources, then record input commit/hash and output
hash. Fail builds on duplicate IDs, unresolved references, invalid probabilities,
non-finite coordinates and impossible item slots. Generate human-readable feature,
command and reducer catalogs from those schemas. Add reducer latency, rejection
reason, connected identity, subscription-row, scheduled-job lag and economy-flow
metrics at the server boundary.

Do not copy QCX's plugin or permission behavior directly. Its Prometheus
`GameTickListener` creates a histogram but does not observe durations, and some
commands marked `CommandNoPermission` have privileged-looking effects. The safe
lesson is the extension seam and generated catalog, coupled to explicit server
authorization and tests proving ordinary identities cannot invoke admin actions.

## Limits of this audit

The emulator snapshots were not built or run, original-client interoperability
was not tested, and external data packs were not loaded. Static test counts are
inventory measures, not pass results. The community-maintained wiki pages index
live features but may omit regional, entitlement, balance or version differences.
Exact implementation contracts still require a small vertical slice, two real
clients, reducer rejection tests, reconnect/disconnect coverage and rendered
Godot verification.
