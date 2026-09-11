//! Runtime loot rolls from the compiled original drop catalog.
//!
//! ``ITEM_MANAGER::CreateDropItem`` builds one kill's loot from four tables and
//! a level-delta percentage. The tables are compiled offline by
//! ``tools/build_drop_catalog.py`` into ``DROP_CATALOG``; this module replays the
//! selection rules against them. The module is authoritative: the client never
//! sends a drop, a vnum or a roll.
//!
//! Deliberate bounds of this slice, all recorded in the catalog's provenance:
//!
//! * Private item-drop rates and premium double-item bonuses are not modelled,
//!   so ``iRandRange`` is the unmodified 4,000,000 and ``iDeltaPercent`` is not
//!   doubled. A future rate system plugs in at [`RollContext`].
//! * The buyer-theit-gloves table only rolls for a premium or unique-group
//!   holder in the original. The selected population has none, so the table is
//!   never rolled and no random value is consumed for it.
//! * ``rare_pct`` on a kill-group row becomes the item's rare attribute in the
//!   original. The current item model has no rare attribute, so the column is
//!   carried by the catalog but not applied.
//!
//! ``ctx.rng()`` is seeded from the reducer timestamp, which is public. Loot is
//! not a secrecy problem — the odds are in the catalog and every drop is
//! audited — but no gameplay decision may rely on predicting it *not* being
//! reproducible, and no security property may depend on the seed.

use crate::definitions;
use crate::inventory::{ItemDrop, item_drop};
use crate::item_security::{self, Cause};
use crate::now_us;
use serde_json::Value;
use spacetimedb::rand::Rng;
use spacetimedb::{Identity, ReducerContext, Table};
use std::collections::HashMap;
use std::sync::OnceLock;

/// ``EMobRank`` order. A rank index past the end has no common table.
pub const MOB_RANKS: [&str; 6] = ["PAWN", "S_PAWN", "KNIGHT", "S_KNIGHT", "BOSS", "KING"];

/// ``MOB_RANK_BOSS``: ranks at or above it use the boss level-delta table for a
/// non-stone mob.
const MOB_RANK_BOSS: u8 = 4;

/// ``iRandRange`` with no private item-drop rate and no unique double-item.
const RAND_RANGE: u32 = 4_000_000;
/// ``iPercent = (pct * iDeltaPercent) / 100`` is integer math on i32.
const PERCENT_SCALE: i32 = 100;
/// ``1 == Random(1, 50000)`` adds 1000 to ``iDeltaPercent``...
const BONUS_RARE_ROLL: u32 = 50_000;
const BONUS_RARE_ADD: i32 = 1000;
/// ...otherwise ``1 == Random(1, 10000)`` adds 500. The two are `else if`.
const BONUS_COMMON_ROLL: u32 = 10_000;
const BONUS_COMMON_ADD: i32 = 500;
/// ``40000 * iDeltaPercent / GetKillPerDrop()``.
const KILL_GROUP_SCALE: i32 = 40_000;
/// The level-item group rolls ``dwPct`` directly, without the level delta.
const LIMIT_ROLL_RANGE: u32 = 1_000_000;

#[derive(Debug)]
struct CommonRow {
    level_start: u8,
    level_end: u8,
    pct_10k: u32,
    vnum: u32,
    count: u16,
}

#[derive(Debug)]
struct PctRow {
    pct_10k: u32,
    vnum: u32,
    count: u16,
}

#[derive(Debug)]
struct KillRow {
    cumulative_pct: u32,
    vnum: u32,
    count: u16,
}

#[derive(Debug, Default)]
struct Group {
    kill_drop: u32,
    level_limit: u32,
    drop: Vec<PctRow>,
    kill: Vec<KillRow>,
    limit: Vec<PctRow>,
}

#[derive(Debug)]
pub struct Tables {
    common: HashMap<String, Vec<CommonRow>>,
    groups: HashMap<u32, Group>,
    normal_percent: [i32; 31],
    boss_percent: [i32; 31],
}

fn catalog() -> &'static Value {
    static CATALOG: OnceLock<Value> = OnceLock::new();
    CATALOG.get_or_init(|| {
        // A checkout without exported drop content builds with an empty
        // catalog. It fails closed: a kill drops no items.
        if definitions::DROP_CATALOG.trim().is_empty() {
            return serde_json::json!({ "common": {}, "groups": {} });
        }
        serde_json::from_str(definitions::DROP_CATALOG)
            .expect("embedded drop catalog must stay valid JSON")
    })
}

/// ``sha256`` of the compiled catalog, for diagnostics and receipts.
pub fn catalog_hash() -> &'static str {
    definitions::DROP_CATALOG_HASH
}

/// Fail at publish time when the embedded catalog cannot roll what it claims.
///
/// ``init`` calls this so a broken catalog is caught while the module is being
/// published instead of by the first kill. A checkout without converted drop
/// content ships an empty catalog and no hash, which stays a valid failure
/// mode: a kill drops nothing rather than guessing.
pub fn validate_content() {
    if definitions::DROP_CATALOG.trim().is_empty() {
        assert!(
            catalog_hash().is_empty(),
            "an empty drop catalog must not carry a content hash"
        );
        return;
    }
    let hash = catalog_hash();
    assert!(
        hash.len() == 64 && hash.bytes().all(|byte| byte.is_ascii_hexdigit()),
        "the drop catalog hash must be a sha256 digest"
    );
    assert_eq!(
        catalog()["content_hash"].as_str(),
        Some(hash),
        "the drop catalog hash must match the embedded catalog"
    );
    let tables = tables();
    assert!(
        !tables.common.is_empty(),
        "a non-empty drop catalog must define common drops"
    );
    assert!(
        tables.normal_percent.iter().any(|percent| *percent > 0)
            && tables.boss_percent.iter().any(|percent| *percent > 0),
        "a non-empty drop catalog must define usable level-delta tables"
    );
}

fn tables() -> &'static Tables {
    static TABLES: OnceLock<Tables> = OnceLock::new();
    TABLES.get_or_init(|| parse_catalog(catalog()))
}

fn percent_table(table: &Value, name: &str) -> [i32; 31] {
    let Some(rows) = table.as_array() else {
        // A checkout without exported drop content compiles to an empty
        // catalog, which carries no level-delta tables either. Nothing can
        // roll against zeros, so the kill still fails closed by dropping no
        // items. Any other shape is a corrupt embedded catalog.
        assert!(
            table.is_null(),
            "drop catalog level_delta.{name} must be an array"
        );
        return [0; 31];
    };
    assert_eq!(
        rows.len(),
        31,
        "drop catalog level_delta.{name} must hold 31 values"
    );
    let mut values = [0i32; 31];
    for (index, value) in rows.iter().enumerate() {
        let percent = value
            .as_u64()
            .filter(|percent| *percent <= 1000)
            .unwrap_or_else(|| panic!("drop catalog level_delta.{name}[{index}] is out of range"));
        values[index] = i32::try_from(percent).expect("a percentage fits i32");
    }
    values
}

fn parse_catalog(document: &Value) -> Tables {
    let mut common = HashMap::new();
    if let Some(ranks) = document["common"].as_object() {
        for (rank, rows) in ranks {
            let parsed = rows
                .as_array()
                .unwrap_or_else(|| panic!("drop catalog common.{rank} must be an array"))
                .iter()
                .map(|row| CommonRow {
                    level_start: u8::try_from(
                        row["level_start"]
                            .as_u64()
                            .expect("common drop row needs a level start"),
                    )
                    .expect("common drop level start fits u8"),
                    level_end: u8::try_from(
                        row["level_end"]
                            .as_u64()
                            .expect("common drop row needs a level end"),
                    )
                    .expect("common drop level end fits u8"),
                    pct_10k: u32::try_from(
                        row["pct_10k"]
                            .as_u64()
                            .expect("common drop row needs a percentage"),
                    )
                    .expect("common drop percentage fits u32"),
                    vnum: u32::try_from(
                        row["vnum"].as_u64().expect("common drop row needs a vnum"),
                    )
                    .expect("common drop vnum fits u32"),
                    count: u16::try_from(row["count"].as_u64().unwrap_or(1))
                        .expect("common drop count fits u16"),
                })
                .collect::<Vec<_>>();
            assert!(
                !parsed.is_empty(),
                "drop catalog common.{rank} must not be empty"
            );
            common.insert(rank.clone(), parsed);
        }
    }
    let mut groups = HashMap::new();
    if let Some(entries) = document["groups"].as_object() {
        for (vnum, group) in entries {
            let mob_vnum: u32 = vnum.parse().expect("drop catalog group keys are mob vnums");
            groups.insert(
                mob_vnum,
                Group {
                    kill_drop: u32::try_from(group["kill_drop"].as_u64().unwrap_or(0))
                        .expect("kill drop weight fits u32"),
                    level_limit: u32::try_from(group["level_limit"].as_u64().unwrap_or(0))
                        .expect("level limit fits u32"),
                    drop: parse_pct_rows(&group["drop"]),
                    kill: parse_kill_rows(&group["kill"]),
                    limit: parse_pct_rows(&group["limit"]),
                },
            );
        }
    }
    let delta = &document["level_delta"];
    Tables {
        common,
        groups,
        normal_percent: percent_table(&delta["normal_percent"], "normal_percent"),
        boss_percent: percent_table(&delta["boss_percent"], "boss_percent"),
    }
}

fn parse_pct_rows(rows: &Value) -> Vec<PctRow> {
    rows.as_array()
        .map(|rows| {
            rows.iter()
                .map(|row| PctRow {
                    pct_10k: u32::try_from(
                        row["pct_10k"]
                            .as_u64()
                            .expect("drop row needs a percentage"),
                    )
                    .expect("drop percentage fits u32"),
                    vnum: u32::try_from(row["vnum"].as_u64().expect("drop row needs a vnum"))
                        .expect("drop vnum fits u32"),
                    count: u16::try_from(row["count"].as_u64().unwrap_or(1))
                        .expect("drop count fits u16"),
                })
                .collect()
        })
        .unwrap_or_default()
}

fn parse_kill_rows(rows: &Value) -> Vec<KillRow> {
    rows.as_array()
        .map(|rows| {
            rows.iter()
                .map(|row| KillRow {
                    cumulative_pct: u32::try_from(
                        row["cumulative_pct"]
                            .as_u64()
                            .expect("kill row needs a cumulative percentage"),
                    )
                    .expect("cumulative percentage fits u32"),
                    vnum: u32::try_from(row["vnum"].as_u64().expect("kill row needs a vnum"))
                        .expect("kill vnum fits u32"),
                    count: u16::try_from(row["count"].as_u64().unwrap_or(1))
                        .expect("kill count fits u16"),
                })
                .collect()
        })
        .unwrap_or_default()
}

/// One roll's inputs. Everything here is server state; a client cannot set it.
pub struct RollContext<'a> {
    pub tables: &'a Tables,
    pub killer_level: u8,
    pub victim_level: u8,
    pub rank: u8,
    pub mob_vnum: u32,
}

/// ``PERCENT_LVDELTA``: ``clamp((victim + 15) - killer, 0, 30)`` selects a
/// percentage from the table ``GetDropPct`` chose for the victim's rank.
pub fn level_delta_percent(
    normal: &[i32; 31],
    boss: &[i32; 31],
    killer_level: u8,
    victim_level: u8,
    rank: u8,
) -> i32 {
    let table = if rank >= MOB_RANK_BOSS { boss } else { normal };
    // The clamp is inside ``PERCENT_LVDELTA``: killing a victim far below the
    // killer's level is ordinary play, not an error.
    let delta = i32::from(victim_level) + 15 - i32::from(killer_level);
    let index = usize::try_from(delta.clamp(0, 30)).expect("a clamped delta fits usize");
    table[index]
}

/// ``(percent * iDeltaPercent) / 100``.
///
/// The original computes this in 32-bit ``int``. The product is widened to 64
/// bits here so a corrupt or future table cannot wrap silently: the pinned rows
/// stay far below the original's overflow point, and a wrapped percentage would
/// hand out loot the pinned table never granted.
fn scaled_percent(pct_10k: u32, delta: i32) -> i64 {
    i64::from(pct_10k) * i64::from(delta) / i64::from(PERCENT_SCALE)
}

/// Common rows for the victim's rank.
///
/// ``ReadCommonDropItemFile`` only fills the four non-boss ranks, so a boss or
/// king has no common table at all and must not fall back to a neighbouring
/// rank's rows.
fn common_rows(tables: &Tables, rank: u8) -> Option<&[CommonRow]> {
    let name = MOB_RANKS.get(usize::from(rank))?;
    tables.common.get(*name).map(Vec::as_slice)
}

/// Roll one kill.
///
/// `draw` returns an inclusive integer range draw, mirroring
/// ``Random::get(low, high)``. It is injected so the selection rules stay pure
/// and deterministic in tests; production passes the reducer RNG. How many
/// draws happen, and in which order, is part of the replayed contract: the
/// bonus rolls come first, then every selected row consumes exactly one draw.
pub fn roll_with<F>(context: &RollContext, mut draw: F) -> Vec<(u32, u16)>
where
    F: FnMut(u32, u32) -> u32,
{
    let mut rolled: Vec<(u32, u16)> = Vec::new();
    let mut delta = level_delta_percent(
        &context.tables.normal_percent,
        &context.tables.boss_percent,
        context.killer_level,
        context.victim_level,
        context.rank,
    );

    // ``GetDropPct``: a rare bonus is an ``elif``, so a rare draw either adds
    // 1000 and consumes exactly one value, or consumes a second value that may
    // add 500.
    if draw(1, BONUS_RARE_ROLL) == 1 {
        delta += BONUS_RARE_ADD;
    } else if draw(1, BONUS_COMMON_ROLL) == 1 {
        delta += BONUS_COMMON_ADD;
    }

    // Common drops. A row outside the killer's level band is skipped *before*
    // its draw, so it consumes no random value — the original ``continue``.
    if let Some(rows) = common_rows(context.tables, context.rank) {
        for row in rows {
            if context.killer_level < row.level_start || context.killer_level > row.level_end {
                continue;
            }
            if scaled_percent(row.pct_10k, delta) >= i64::from(draw(1, RAND_RANGE)) {
                rolled.push((row.vnum, row.count));
            }
        }
    }

    let Some(group) = context.tables.groups.get(&context.mob_vnum) else {
        return rolled;
    };

    // ``CDropItemGroup``: per-row percentages with no level filter.
    for row in &group.drop {
        if scaled_percent(row.pct_10k, delta) >= i64::from(draw(1, RAND_RANGE)) {
            rolled.push((row.vnum, row.count));
        }
    }

    // ``CMobItemGroup``: one roll against the group's share of kills, then one
    // cumulative pick when it passes.
    if !group.kill.is_empty() && group.kill_drop > 0 {
        let percent = i64::from(KILL_GROUP_SCALE) * i64::from(delta) / i64::from(group.kill_drop);
        if percent >= i64::from(draw(1, RAND_RANGE)) {
            let last = group
                .kill
                .last()
                .expect("the kill group was just checked to be non-empty")
                .cumulative_pct;
            let pick = draw(1, last);
            if let Some(row) = group.kill.iter().find(|row| row.cumulative_pct >= pick) {
                rolled.push((row.vnum, row.count));
            }
        }
    }

    // ``CLevelItemGroup``: gated on the killer's level, and its rows roll their
    // raw percentage without the level delta. The original rolls the whole
    // group, so a level-limited group with no rows consumes nothing.
    if group.level_limit <= u32::from(context.killer_level) {
        for row in &group.limit {
            if row.pct_10k >= draw(1, LIMIT_ROLL_RANGE) {
                rolled.push((row.vnum, row.count));
            }
        }
    }

    rolled
}

/// Roll one kill's items with the reducer RNG.
pub fn roll(
    ctx: &ReducerContext,
    killer_level: u8,
    victim_level: u8,
    rank: u8,
    mob_vnum: u32,
) -> Vec<(u32, u16)> {
    let context = RollContext {
        tables: tables(),
        killer_level,
        victim_level,
        rank,
        mob_vnum,
    };
    roll_with(&context, |low, high| {
        if low >= high {
            // ``Random::get`` is inclusive; the pinned tables always pass a
            // range, but a degenerate one must not panic inside a reducer.
            low
        } else {
            ctx.rng().gen_range(low..=high)
        }
    })
}

/// Insert one rolled item as a ground drop with its audit record.
pub fn drop_items(
    ctx: &ReducerContext,
    owner: Identity,
    position: (f32, f32, f32),
    items: &[(u32, u16)],
) {
    let now = now_us(ctx);
    for (vnum, count) in items {
        let drop = ctx.db.item_drop().insert(ItemDrop {
            id: 0,
            x: position.0,
            y: position.1,
            z: position.2,
            vnum: *vnum,
            count: *count,
            owner,
            reserved_until_us: now.saturating_add(GROUND_RESERVED_US),
            expires_at_us: now.saturating_add(GROUND_EXPIRES_US),
        });
        item_security::ground(ctx, &drop, true, Cause::Monster);
    }
}

const GROUND_RESERVED_US: i64 = 10_000_000;
const GROUND_EXPIRES_US: i64 = 60_000_000;

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::VecDeque;

    /// Draws a scripted sequence and records every range the roll asked for.
    ///
    /// An exhausted script answers with the range's upper bound, which never
    /// passes a percentage comparison, so an unexpected extra draw shows up as
    /// a missing item or a wrong call count instead of a panic.
    struct Script {
        values: VecDeque<u32>,
        calls: Vec<(u32, u32)>,
    }

    impl Script {
        fn new(values: &[u32]) -> Self {
            Self {
                values: values.iter().copied().collect(),
                calls: Vec::new(),
            }
        }

        fn draw(&mut self, low: u32, high: u32) -> u32 {
            self.calls.push((low, high));
            self.values.pop_front().unwrap_or(high)
        }
    }

    fn common(level_start: u8, level_end: u8, pct_10k: u32, vnum: u32) -> CommonRow {
        CommonRow {
            level_start,
            level_end,
            pct_10k,
            vnum,
            count: 1,
        }
    }

    fn pct(pct_10k: u32, vnum: u32) -> PctRow {
        PctRow {
            pct_10k,
            vnum,
            count: 1,
        }
    }

    fn kill(cumulative_pct: u32, vnum: u32) -> KillRow {
        KillRow {
            cumulative_pct,
            vnum,
            count: 1,
        }
    }

    /// A table set with the same level-delta percentages the pinned file has at
    /// index 15 (victim 10 against killer 10): normal 100, boss 105.
    fn tables(common: HashMap<String, Vec<CommonRow>>, groups: HashMap<u32, Group>) -> Tables {
        let mut normal_percent = [0i32; 31];
        normal_percent[15] = 100;
        let mut boss_percent = [0i32; 31];
        boss_percent[15] = 105;
        Tables {
            common,
            groups,
            normal_percent,
            boss_percent,
        }
    }

    fn rank_common(rank: &str, rows: Vec<CommonRow>) -> HashMap<String, Vec<CommonRow>> {
        let mut common = HashMap::new();
        common.insert(rank.to_owned(), rows);
        common
    }

    fn context<'a>(tables: &'a Tables, rank: u8, mob_vnum: u32) -> RollContext<'a> {
        RollContext {
            tables,
            killer_level: 10,
            victim_level: 10,
            rank,
            mob_vnum,
        }
    }

    fn roll(context: &RollContext, values: &[u32]) -> (Vec<(u32, u16)>, Script) {
        let mut script = Script::new(values);
        let rolled = roll_with(context, |low, high| script.draw(low, high));
        (rolled, script)
    }

    /// The bonus rolls consume exactly one draw on a rare hit and exactly two
    /// otherwise, because the second roll is an ``else if``.
    #[test]
    fn bonus_rolls_short_circuit() {
        let tables = tables(HashMap::new(), HashMap::new());
        let context = context(&tables, 0, 0);

        let (rolled, script) = roll(&context, &[1]);
        assert!(rolled.is_empty());
        assert_eq!(script.calls, [(1, BONUS_RARE_ROLL)]);

        let (_, script) = roll(&context, &[2, 1]);
        assert_eq!(script.calls, [(1, BONUS_RARE_ROLL), (1, BONUS_COMMON_ROLL)]);

        let (_, script) = roll(&context, &[2, 2]);
        assert_eq!(script.calls.len(), 2);
    }

    /// The rare bonus is observable: a 1% row only passes once the +1000 delta
    /// has been added, so the same draw fails without it.
    #[test]
    fn rare_bonus_raises_the_common_percentage() {
        let tables = tables(
            rank_common("PAWN", vec![common(1, 20, 1, 777)]),
            HashMap::new(),
        );
        let context = context(&tables, 0, 0);

        // Rare roll hits, row draw is 11: scaled 1 * 1100 / 100 = 11 passes.
        let (rolled, script) = roll(&context, &[1, 11]);
        assert_eq!(rolled, [(777, 1)]);
        assert_eq!(script.calls.len(), 2);

        // Same row draw without the bonus: 1 * 100 / 100 = 1 fails.
        let (rolled, script) = roll(&context, &[2, 2, 11]);
        assert!(rolled.is_empty());
        assert_eq!(script.calls.len(), 3);
    }

    /// A row outside the killer's level band is skipped before its draw, so it
    /// consumes no random value. Rows in the band each consume exactly one.
    #[test]
    fn common_rows_outside_the_level_band_consume_nothing() {
        let tables = tables(
            rank_common(
                "PAWN",
                vec![
                    common(1, 5, 100, 100),
                    common(10, 20, 100, 200),
                    common(1, 5, 100, 300),
                ],
            ),
            HashMap::new(),
        );
        let context = context(&tables, 0, 0);

        // Bonus rolls do not hit, then the single in-band row draws 1 and
        // passes against the 100% row.
        let (rolled, script) = roll(&context, &[2, 2, 1]);
        assert_eq!(rolled, [(200, 1)]);
        assert_eq!(
            script.calls,
            [
                (1, BONUS_RARE_ROLL),
                (1, BONUS_COMMON_ROLL),
                (1, RAND_RANGE)
            ]
        );
    }

    /// BOSS and KING mobs have no common table, and neither does a rank index
    /// past the end of ``EMobRank``. A row of another rank must not leak in.
    #[test]
    fn common_rows_require_the_exact_rank() {
        let tables = tables(
            rank_common("PAWN", vec![common(1, 20, 10_000, 100)]),
            HashMap::new(),
        );

        let (rolled, script) = roll(&context(&tables, MOB_RANK_BOSS, 0), &[2, 2]);
        assert!(rolled.is_empty());
        assert_eq!(script.calls.len(), 2);

        let (rolled, script) = roll(&context(&tables, 5, 0), &[2, 2]);
        assert!(rolled.is_empty());
        assert_eq!(script.calls.len(), 2);

        let (rolled, script) = roll(&context(&tables, 6, 0), &[2, 2]);
        assert!(rolled.is_empty());
        assert_eq!(script.calls.len(), 2);

        // The same table does pay out for a PAWN, so the fixture is meaningful.
        let (rolled, _) = roll(&context(&tables, 0, 0), &[2, 2, 1]);
        assert_eq!(rolled, [(100, 1)]);
    }

    /// ``PERCENT_LVDELTA`` clamps the killer's lead to 30 and selects the boss
    /// table for rank >= ``MOB_RANK_BOSS``.
    #[test]
    fn level_delta_selects_the_rank_table_and_clamps() {
        let mut normal = [0i32; 31];
        normal[15] = 100;
        normal[30] = 180;
        let mut boss = [0i32; 31];
        boss[15] = 105;
        boss[30] = 180;

        assert_eq!(level_delta_percent(&normal, &boss, 10, 10, 0), 100);
        assert_eq!(
            level_delta_percent(&normal, &boss, 10, 10, MOB_RANK_BOSS),
            105
        );
        assert_eq!(level_delta_percent(&normal, &boss, 10, 10, 5), 105);

        // A victim more than 15 levels above the killer clamps to the top row.
        assert_eq!(level_delta_percent(&normal, &boss, 1, 100, 0), 180);
        // A victim far below uses row 0, which the fixture leaves at 0.
        assert_eq!(level_delta_percent(&normal, &boss, 100, 1, 0), 0);
    }

    /// The kill group is one gate roll against the mob's share of kills and,
    /// on a pass, one cumulative pick that resolves to the first row whose
    /// cumulative percentage reaches the draw.
    #[test]
    fn kill_group_gates_then_picks_the_first_cumulative_row() {
        let mut group = Group {
            kill_drop: 800,
            ..Group::default()
        };
        group.kill = vec![kill(30, 5), kill(100, 7)];
        let mut groups = HashMap::new();
        groups.insert(301u32, group);
        let tables = tables(HashMap::new(), groups);
        let context = context(&tables, 0, 301);

        // 40000 * 100 / 800 = 5000, so a gate draw of 1 passes.
        let (rolled, script) = roll(&context, &[2, 2, 1, 60]);
        assert_eq!(rolled, [(7, 1)]);
        assert_eq!(script.calls[2], (1, RAND_RANGE));
        assert_eq!(script.calls[3], (1, 100));

        let (rolled, _) = roll(&context, &[2, 2, 1, 30]);
        assert_eq!(rolled, [(5, 1)]);
        let (rolled, _) = roll(&context, &[2, 2, 1, 31]);
        assert_eq!(rolled, [(7, 1)]);

        // A failing gate consumes the gate draw only.
        let (rolled, script) = roll(&context, &[2, 2, 5001, 1]);
        assert!(rolled.is_empty());
        assert_eq!(script.calls.len(), 3);
    }

    /// A kill group with no kill weight never rolls, so the shared RNG stream
    /// keeps the original shape for mobs the pinned tables give no share.
    #[test]
    fn kill_group_without_weight_does_not_roll() {
        let mut group = Group {
            kill_drop: 0,
            ..Group::default()
        };
        group.kill = vec![kill(100, 5)];
        let mut groups = HashMap::new();
        groups.insert(103u32, group);
        let tables = tables(HashMap::new(), groups);

        let (rolled, script) = roll(&context(&tables, 0, 103), &[2, 2, 1]);
        assert!(rolled.is_empty());
        assert_eq!(script.calls.len(), 2);
    }

    /// The level-item group is gated on the killer's level and rolls its raw
    /// percentage without the level delta.
    #[test]
    fn level_limit_group_gates_on_the_killer_level() {
        let mut group = Group {
            level_limit: 30,
            ..Group::default()
        };
        group.limit = vec![pct(500_000, 9)];
        let mut groups = HashMap::new();
        groups.insert(304u32, group);
        let tables = tables(HashMap::new(), groups);

        let mut below = context(&tables, 0, 304);
        below.killer_level = 29;
        let (rolled, script) = roll(&below, &[2, 2, 1]);
        assert!(rolled.is_empty());
        assert_eq!(script.calls.len(), 2);

        let mut at_limit = context(&tables, 0, 304);
        at_limit.killer_level = 30;
        let (rolled, script) = roll(&at_limit, &[2, 2, 100]);
        assert_eq!(rolled, [(9, 1)]);
        assert_eq!(script.calls[2], (1, LIMIT_ROLL_RANGE));

        // The group rolls its raw percentage, so a draw above it fails even
        // though the level delta is far below 1.
        let (rolled, _) = roll(&at_limit, &[2, 2, 500_001]);
        assert!(rolled.is_empty());
    }

    /// The scaled percentage is computed in 64-bit so a corrupt table cannot
    /// wrap silently into granting loot.
    #[test]
    fn scaled_percent_widens_before_dividing() {
        assert_eq!(scaled_percent(10_000, 100), 10_000);
        assert_eq!(scaled_percent(1, 1100), 11);
        // 1_000_000_000 * 1000 / 100 overflows i32; it must not wrap.
        assert_eq!(scaled_percent(1_000_000_000, 1000), 10_000_000_000);
    }
}
