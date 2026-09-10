//! Authoritative, data-driven quest execution.
//!
//! The compiled catalog in `definitions::QUEST_CATALOG` is the single source of
//! quest states, dialogues and rewards. This module owns the runtime: it maps
//! gameplay events (login, level-up, monster death, NPC conversation) onto the
//! compiled triggers, applies the resulting state changes and rewards in one
//! transaction, and keeps every row account-private.
//!
//! Ordering rules that the original scripts depend on and that this module
//! enforces:
//! * Event evaluation walks the quest order, so a lower-numbered quest may
//!   advance a later quest through `set_quest_state`.
//! * Ops execute in script order. A counter that reaches its total runs its
//!   `on_reached` ops before the remaining ops of the same trigger.
//! * A state's `enter` ops run on the transition that reaches it, and their
//!   dialogue supersedes the scripted lines of the triggering trigger.
//! * Reward ops are transactional. If a grant fails the whole reducer rolls
//!   back, so a quest can never advance without its reward.
//!
//! Exactly-once behaviour comes from the state machine plus the reducer
//! transaction, not from a persisted replay table: a trigger that has already
//! moved the character to another state cannot match again, and a second
//! delivery inside one transaction is suppressed by the per-delivery `fired`
//! set. Nothing here may be replayed by a later tick.

use crate::item_security::Cause;
// `character_progression` and `player` are foreign tables here, so their traits
// must be in scope to use `ctx.db`.
use crate::progression::character_progression;
use crate::{definitions, inventory, item_catalog, now_us, player, progression};
use serde_json::Value;
use spacetimedb::rand::Rng;
use spacetimedb::{Filter, Identity, ReducerContext, Table};
use std::collections::VecDeque;
use std::sync::OnceLock;

/// Upper bound on state entries chained by one gameplay event. The opening
/// catalog chains at most two; the bound keeps a future content mistake from
/// looping inside a reducer transaction.
const MAX_STATE_ENTERS: usize = 64;
/// How long an unanswered scripted question stays valid.
const SELECTION_US: i64 = 120_000_000;
/// Marker state every compiled quest ends in.
const COMPLETE: &str = "__COMPLETE__";

#[spacetimedb::table(accessor = quest_state, public)]
#[derive(Clone)]
pub struct QuestState {
    #[primary_key]
    pub id: u64,
    #[index(btree)]
    pub character_id: Identity,
    #[index(btree)]
    pub account: Identity,
    pub quest_index: u16,
    pub quest_id: String,
    pub title: String,
    pub state: String,
    /// Monotonic revision of this quest's state, so a client or test can tell
    /// one transition from a duplicate delivery.
    pub sequence: u32,
    pub started_at_us: i64,
    pub updated_at_us: i64,
}

/// One row per quest the character is currently tracking, so several quests can
/// hand out letters at the same time, exactly like the original letter list.
#[spacetimedb::table(accessor = quest_objective, public)]
#[derive(Clone)]
pub struct QuestObjective {
    #[primary_key]
    pub id: u64,
    #[index(btree)]
    pub character_id: Identity,
    #[index(btree)]
    pub account: Identity,
    pub quest_index: u16,
    pub quest_id: String,
    /// Title of the active letter, empty when the quest hands out no letter.
    pub letter_title: String,
    /// Objective or target label shown next to the tracker entry.
    pub label: String,
    /// NPC the tracker points at, zero when the objective is not an NPC.
    pub target_vnum: u32,
    pub amount: u32,
    pub total: u32,
    pub remaining_display: bool,
    pub updated_at_us: i64,
}

/// A pending scripted question. Options are rendered by the client; the branch
/// bodies stay server-side so a client cannot pick an answer that was never
/// offered.
#[spacetimedb::table(accessor = quest_selection, public)]
#[derive(Clone)]
pub struct QuestSelection {
    #[primary_key]
    pub character_id: Identity,
    pub account: Identity,
    pub npc_vnum: u32,
    pub quest_index: u16,
    pub options: Vec<String>,
    pub branches_json: String,
    pub created_at_us: i64,
    pub expires_at_us: i64,
}

#[spacetimedb::client_visibility_filter]
const OWN_QUEST_STATE: Filter =
    Filter::Sql("SELECT * FROM quest_state WHERE quest_state.account = :sender");
#[spacetimedb::client_visibility_filter]
const OWN_QUEST_OBJECTIVE: Filter =
    Filter::Sql("SELECT * FROM quest_objective WHERE quest_objective.account = :sender");
#[spacetimedb::client_visibility_filter]
const OWN_QUEST_SELECTION: Filter =
    Filter::Sql("SELECT * FROM quest_selection WHERE quest_selection.account = :sender");

fn catalog() -> &'static Value {
    static CATALOG: OnceLock<Value> = OnceLock::new();
    CATALOG.get_or_init(|| {
        // A checkout without exported quest content builds with an empty
        // catalog. It fails closed: no quest starts and no trigger fires.
        if definitions::QUEST_CATALOG.trim().is_empty() {
            return serde_json::json!({ "order": [], "quests": {} });
        }
        serde_json::from_str(definitions::QUEST_CATALOG)
            .expect("embedded quest catalog must stay valid JSON")
    })
}

fn order() -> &'static [Value] {
    catalog()["order"].as_array().map_or(&[], Vec::as_slice)
}

/// Stable catalog index of a quest id, used as the row identity everywhere.
pub fn quest_index(id: &str) -> Option<u16> {
    order()
        .iter()
        .position(|entry| entry.as_str() == Some(id))
        .map(|index| u16::try_from(index).expect("quest catalog fits u16"))
}

fn quest_id(index: u16) -> Option<&'static str> {
    order().get(usize::from(index))?.as_str()
}

fn quest_doc(index: u16) -> Option<&'static Value> {
    catalog()["quests"].get(quest_id(index)?)
}

fn quest_title(index: u16) -> String {
    quest_doc(index)
        .and_then(|quest| quest["title"].as_str())
        .map_or_else(|| quest_id(index).unwrap_or_default().to_owned(), clean)
}

fn state_doc(index: u16, state: &str) -> Option<&'static Value> {
    quest_doc(index)?["states"].get(state)
}

/// Content hash the client compares against its own compiled catalog.
pub fn catalog_hash() -> &'static str {
    definitions::QUEST_CATALOG_HASH
}

pub fn validate_content() {
    for (index, entry) in order().iter().enumerate() {
        let index = u16::try_from(index).expect("quest catalog fits u16");
        let id = entry.as_str().expect("quest order entries must be names");
        let quest = quest_doc(index).unwrap_or_else(|| panic!("quest {id} must resolve"));
        let states = quest["states"]
            .as_object()
            .unwrap_or_else(|| panic!("quest {id} states must be an object"));
        // `run` is the usual first playing state, but the opening quest starts
        // in `start` and advances on its first login trigger. A quest unlocked
        // by another quest can instead pin its entry point with a catalog
        // `initial_state`, because it has no login/level-up trigger of its own.
        // Whichever source wins must still name a declared state, and every
        // quest must be able to reach its terminal state.
        let entry = initial_state(index);
        assert!(
            states.contains_key(&entry),
            "quest {id} initial state {entry} must exist"
        );
        assert!(
            states.contains_key(COMPLETE),
            "quest {id} needs a {COMPLETE} state"
        );
        for (name, state) in states {
            for op in state["enter"]
                .as_array()
                .unwrap_or_else(|| panic!("quest {id}.{name} enter ops must be an array"))
            {
                validate_op(op, &format!("{id}.{name}.enter"));
            }
            assert_state_targets(
                state["enter"].clone(),
                states,
                &format!("{id}.{name}.enter"),
            );
            for trigger in state["triggers"]
                .as_array()
                .unwrap_or_else(|| panic!("quest {id}.{name} triggers must be an array"))
            {
                assert!(
                    !trigger["event"].as_str().unwrap_or_default().is_empty(),
                    "quest {id}.{name} triggers need an event"
                );
                for op in trigger["ops"]
                    .as_array()
                    .unwrap_or_else(|| panic!("quest {id}.{name} trigger ops must be an array"))
                {
                    validate_op(op, &format!("{id}.{name}"));
                }
                assert_state_targets(
                    trigger["ops"].clone(),
                    states,
                    &format!("{id}.{name} trigger"),
                );
            }
        }
    }
}

fn assert_state_targets(ops: Value, states: &serde_json::Map<String, Value>, label: &str) {
    let Some(ops) = ops.as_array() else {
        return;
    };
    for op in ops {
        match op["op"].as_str().unwrap_or_default() {
            "set_state" => assert!(
                op["state"]
                    .as_str()
                    .is_some_and(|state| states.contains_key(state)),
                "{label} targets a state the quest does not declare"
            ),
            "count" => assert_state_targets(op["on_reached"].clone(), states, label),
            "select" => {
                for branch in op["branches"].as_array().into_iter().flatten() {
                    assert_state_targets(branch.clone(), states, label);
                }
            }
            _ => {}
        }
    }
}

fn validate_op(op: &Value, label: &str) {
    let kind = op["op"].as_str().unwrap_or_default();
    assert!(!kind.is_empty(), "{label} has an op without a kind");
    match kind {
        "count" => {
            let total = op["total"].as_u64().expect("count total");
            assert!(
                (1..=100_000).contains(&total),
                "{label}.count total out of range"
            );
            for nested in op["on_reached"].as_array().expect("on_reached ops") {
                validate_op(nested, label);
            }
        }
        "select" => {
            let options = op["options"].as_array().expect("select options");
            let branches = op["branches"].as_array().expect("select branches");
            assert_eq!(
                options.len(),
                branches.len(),
                "{label} option/branch mismatch"
            );
            assert!(
                (1..=8).contains(&options.len()),
                "{label} option count out of range"
            );
            for branch in branches {
                for nested in branch.as_array().expect("select branch ops") {
                    validate_op(nested, label);
                }
            }
        }
        "objective" => {
            let total = op["total"].as_u64().expect("objective total");
            assert!(
                (1..=100_000).contains(&total),
                "{label}.objective total out of range"
            );
        }
        "set_state" => assert!(
            !op["state"].as_str().unwrap_or_default().is_empty(),
            "{label}.set_state needs a state"
        ),
        "give_exp" | "give_money" | "say_reward_value" => {
            let amount = op["amount"].as_u64().expect("reward amount");
            assert!(amount <= 10_000_000, "{label} reward amount out of range");
        }
        "give_item" | "remove_item" => {
            let count = op["count"].as_u64().expect("item count");
            assert!(
                (1..=u64::from(u16::MAX)).contains(&count),
                "{label} item count out of range"
            );
        }
        _ => {}
    }
}

/// Rendered conversation an NPC interaction should present.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Dialogue {
    pub title: String,
    pub lines: Vec<String>,
    pub options: Vec<String>,
    /// Last item offered as a reward, so `say_item` can reuse its quantity.
    reward_item: Option<(u32, u32)>,
}

impl Dialogue {
    pub fn body(&self) -> String {
        self.lines.join("\n")
    }

    pub fn is_empty(&self) -> bool {
        self.lines.is_empty() && self.options.is_empty()
    }

    fn push(&mut self, line: &str) {
        let line = clean(line);
        if !line.trim().is_empty() {
            self.lines.push(line);
        }
    }

    fn push_reward(&mut self, rendered: String) {
        if self.lines.last() == Some(&rendered) {
            return;
        }
        self.push(&rendered);
    }

    fn set_title(&mut self, title: &str) {
        if self.title.is_empty() {
            self.title = clean(title);
        }
    }

    /// Collect another dialogue's content, keeping the first title.
    fn absorb(&mut self, other: Dialogue) {
        if !other.title.is_empty() {
            self.set_title(&other.title);
        }
        for line in &other.lines {
            self.push(line);
        }
        for option in &other.options {
            if !self.options.iter().any(|existing| existing == option) {
                self.options.push(option.clone());
            }
        }
        if other.reward_item.is_some() {
            self.reward_item = other.reward_item;
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Event {
    Login,
    LevelUp,
    Kill { vnum: u32 },
    NpcClick { vnum: u32 },
    NpcChat { vnum: u32 },
}

impl Event {
    fn name(self) -> &'static str {
        match self {
            Self::Login => "login",
            Self::LevelUp => "levelup",
            Self::Kill { .. } => "kill",
            Self::NpcClick { .. } => "npc_click",
            Self::NpcChat { .. } => "npc_chat",
        }
    }

    fn vnum(self) -> Option<u32> {
        match self {
            Self::Kill { vnum } | Self::NpcClick { vnum } | Self::NpcChat { vnum } => Some(vnum),
            _ => None,
        }
    }
}

fn state_rows(ctx: &ReducerContext, character: Identity) -> Vec<QuestState> {
    let mut rows: Vec<_> = ctx
        .db
        .quest_state()
        .character_id()
        .filter(character)
        .collect();
    rows.sort_by_key(|row| row.quest_index);
    rows
}

fn state_row_for(ctx: &ReducerContext, character: Identity, index: u16) -> Option<QuestState> {
    state_rows(ctx, character)
        .into_iter()
        .find(|row| row.quest_index == index)
}

fn write_state_row(ctx: &ReducerContext, row: QuestState) {
    if ctx.db.quest_state().id().find(row.id).is_some() {
        ctx.db.quest_state().id().update(row);
    } else {
        ctx.db.quest_state().insert(row);
    }
}

// `next_row_id` scans the table. Both quest tables are bounded by the compiled
// catalog (4 quests today) plus one pending question, so the scan is tiny.
fn next_state_id(ctx: &ReducerContext) -> u64 {
    ctx.db
        .quest_state()
        .iter()
        .map(|row| row.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1)
}

fn next_tracker_id(ctx: &ReducerContext) -> u64 {
    ctx.db
        .quest_objective()
        .iter()
        .map(|row| row.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1)
}

/// First playing state of a compiled quest.
///
/// Almost every quest begins in `run`, which carries the login/level-up
/// triggers that arm the opening conversation. The first main quest has no
/// `run` at all: it starts in `start` and its first login trigger moves it to
/// `gotoinfomation`. A quest that another quest unlocks (through
/// `set_quest_state`) has no login trigger of its own, so its catalog entry
/// pins the state the joining character waits in. Prefer that explicit
/// override, then `run` so existing quests keep their behaviour, then `start`,
/// then the first declared state of a catalog whose states happen to be
/// ordered.
fn initial_state(index: u16) -> String {
    let quest = quest_doc(index);
    let states = quest.and_then(|quest| quest["states"].as_object());
    let Some(states) = states else {
        return "run".into();
    };
    if let Some(declared) = quest.and_then(|quest| quest["initial_state"].as_str())
        && states.contains_key(declared)
    {
        return declared.to_owned();
    }
    for candidate in ["run", "start"] {
        if states.contains_key(candidate) {
            return candidate.into();
        }
    }
    states
        .keys()
        .next()
        .cloned()
        .unwrap_or_else(|| "run".into())
}

fn create_state_row(
    ctx: &ReducerContext,
    character: Identity,
    account: Identity,
    index: u16,
    now: i64,
) -> QuestState {
    QuestState {
        id: next_state_id(ctx),
        character_id: character,
        account,
        quest_index: index,
        quest_id: quest_id(index).unwrap_or_default().to_owned(),
        title: quest_title(index),
        state: initial_state(index),
        sequence: 1,
        started_at_us: now,
        updated_at_us: now,
    }
}

fn account_of(ctx: &ReducerContext, character: Identity) -> Result<Identity, String> {
    crate::accounts::owner_account(ctx, character)
        .ok_or_else(|| "Quest state requires an account.".to_string())
}

/// Create the catalog rows for a joining character and fire login triggers.
pub fn enter(ctx: &ReducerContext, character: Identity) -> Result<(), String> {
    if order().is_empty() {
        return Ok(());
    }
    let account = account_of(ctx, character)?;
    let now = now_us(ctx);
    for index in 0..order().len() {
        let index = u16::try_from(index).map_err(|_| "Quest catalog is too large.")?;
        if state_row_for(ctx, character, index).is_some() {
            continue;
        }
        let row = create_state_row(ctx, character, account, index, now);
        let state = row.state.clone();
        write_state_row(ctx, row);
        run_state_enter(ctx, character, index, &state)?;
    }
    dispatch(ctx, character, Event::Login, 6)?;
    Ok(())
}

/// Run one state's `enter` ops. Called when a row is first created and from
/// `drain_enters` after a transition reaches the state.
fn run_state_enter(
    ctx: &ReducerContext,
    character: Identity,
    index: u16,
    state: &str,
) -> Result<(), String> {
    let mut outcome = Outcome::default();
    let mut dialogue = Dialogue::default();
    apply_state_enter(ctx, character, index, state, &mut outcome, &mut dialogue)?;
    drain_enters(ctx, character, &mut outcome)
}

/// Expire pending questions whose character logged out or never answered.
pub fn maintain(ctx: &ReducerContext) -> Result<(), String> {
    let now = now_us(ctx);
    let expired: Vec<Identity> = ctx
        .db
        .quest_selection()
        .iter()
        .filter(|row| row.expires_at_us <= now)
        .map(|row| row.character_id)
        .collect();
    for character in expired {
        ctx.db.quest_selection().character_id().delete(character);
    }
    Ok(())
}

/// Fire a monster-death event. A failed reward never aborts the kill itself.
pub fn on_kill(ctx: &ReducerContext, character: Identity, vnum: u32) {
    let _ = dispatch(ctx, character, Event::Kill { vnum }, 1);
}

pub fn on_level_up(ctx: &ReducerContext, character: Identity) {
    let _ = dispatch(ctx, character, Event::LevelUp, 6);
}

/// Resolve the dialogue an NPC interaction should present and apply the quest
/// effects of that interaction. A click is tried first; when the quest scripts
/// answer only to conversation, the chat event is delivered in the same
/// reducer transaction.
pub fn on_npc_click(
    ctx: &ReducerContext,
    character: Identity,
    vnum: u32,
) -> Result<Dialogue, String> {
    if order().is_empty() {
        return Ok(Dialogue::default());
    }
    let dialogue = dispatch(ctx, character, Event::NpcClick { vnum }, 10)?;
    if !dialogue.is_empty() {
        return Ok(dialogue);
    }
    dispatch(ctx, character, Event::NpcChat { vnum }, 6)
}

/// Apply the answer to a pending scripted question.
pub fn on_npc_choose(
    ctx: &ReducerContext,
    character: Identity,
    npc_vnum: u32,
    option: u32,
) -> Result<Dialogue, String> {
    let selection = ctx
        .db
        .quest_selection()
        .character_id()
        .find(character)
        .ok_or("That answer is no longer being asked.")?;
    if selection.expires_at_us <= now_us(ctx) {
        ctx.db.quest_selection().character_id().delete(character);
        return Err("That answer is no longer being asked.".into());
    }
    if selection.npc_vnum != 0 && selection.npc_vnum != npc_vnum {
        return Err("That answer belongs to another conversation.".into());
    }
    let branches: Value = serde_json::from_str(&selection.branches_json)
        .map_err(|_| "Stored question is invalid.")?;
    let branch = branches
        .as_array()
        .and_then(|branches| branches.get(usize::try_from(option).ok()?))
        .cloned()
        .ok_or("Unknown dialogue answer.")?;
    ctx.db.quest_selection().character_id().delete(character);
    let index = selection.quest_index;
    let mut row = state_row_for(ctx, character, index).ok_or("That quest is not available.")?;
    let mut outcome = Outcome {
        npc_vnum,
        ..Outcome::default()
    };
    run_ops(ctx, character, index, &mut row, &branch, &mut outcome)?;
    drain_enters(ctx, character, &mut outcome)?;
    Ok(presented(outcome))
}

#[derive(Default)]
struct Outcome {
    /// Text the player's own action produced: NPC speech and answered questions.
    dialogue: Dialogue,
    /// Text from states this delivery reached as a consequence. It is presented
    /// only when the action itself produced nothing, so clicking an NPC still
    /// reads as that NPC's conversation instead of a quest notice.
    notice: Dialogue,
    /// States that must run their `enter` ops after the current pass.
    queue: VecDeque<(u16, String)>,
    npc_vnum: u32,
    granted: bool,
}

/// The conversation a delivery presents: the interaction's own text when there
/// is any, otherwise the notice from the states it reached.
fn presented(outcome: Outcome) -> Dialogue {
    if outcome.dialogue.is_empty() {
        outcome.notice
    } else {
        outcome.dialogue
    }
}

fn dispatch(
    ctx: &ReducerContext,
    character: Identity,
    event: Event,
    passes: u8,
) -> Result<Dialogue, String> {
    if order().is_empty() {
        return Ok(Dialogue::default());
    }
    let level = ctx
        .db
        .character_progression()
        .character_id()
        .find(character)
        .map_or(1, |row| row.level);
    let mut outcome = Outcome {
        npc_vnum: event.vnum().unwrap_or(0),
        ..Outcome::default()
    };
    // Triggers already delivered by this event. The state row identifies
    // progress across ticks; this set only stops a single delivery from
    // matching the same trigger slot twice.
    let mut fired: Vec<(u16, u32)> = Vec::new();
    for _ in 0..passes {
        let mut progressed = false;
        for index in 0..order().len() {
            let Ok(index) = u16::try_from(index) else {
                break;
            };
            let Some(mut row) = state_row_for(ctx, character, index) else {
                continue;
            };
            if row.state == COMPLETE {
                continue;
            }
            let Some(document) = state_doc(index, &row.state) else {
                continue;
            };
            let Some(triggers) = document["triggers"].as_array() else {
                continue;
            };
            for (slot, trigger) in triggers.iter().enumerate() {
                if trigger["event"].as_str() != Some(event.name()) {
                    continue;
                }
                let slot = u32::try_from(slot).unwrap_or(u32::MAX);
                if fired.contains(&(index, slot)) {
                    continue;
                }
                if !conditions_hold(ctx, character, &row, event, level, trigger) {
                    continue;
                }
                fired.push((index, slot));
                run_ops(
                    ctx,
                    character,
                    index,
                    &mut row,
                    &trigger["ops"],
                    &mut outcome,
                )?;
                progressed = true;
            }
        }
        drain_enters(ctx, character, &mut outcome)?;
        if !progressed {
            break;
        }
    }
    Ok(presented(outcome))
}

/// Apply one state's `enter` ops to an existing row and collect its dialogue.
fn apply_state_enter(
    ctx: &ReducerContext,
    character: Identity,
    index: u16,
    state: &str,
    outcome: &mut Outcome,
    dialogue: &mut Dialogue,
) -> Result<(), String> {
    let Some(mut row) = state_row_for(ctx, character, index) else {
        return Ok(());
    };
    // A later transition in the same delivery supersedes this entry.
    if row.state != state {
        return Ok(());
    }
    let Some(document) = state_doc(index, state) else {
        return Ok(());
    };
    let Some(ops) = document["enter"].as_array() else {
        return Ok(());
    };
    let has_objective = ops.iter().any(|op| op["op"].as_str() == Some("objective"));
    run_ops_collecting(
        ctx,
        character,
        index,
        &mut row,
        &document["enter"],
        outcome,
        dialogue,
    )?;
    if !has_objective {
        clear_tracker_progress(ctx, character, index);
    }
    Ok(())
}

fn drain_enters(
    ctx: &ReducerContext,
    character: Identity,
    outcome: &mut Outcome,
) -> Result<(), String> {
    let mut entered = 0usize;
    while let Some((index, state)) = outcome.queue.pop_front() {
        if entered >= MAX_STATE_ENTERS {
            break;
        }
        entered += 1;
        let mut dialogue = Dialogue::default();
        apply_state_enter(ctx, character, index, &state, outcome, &mut dialogue)?;
        outcome.notice.absorb(dialogue);
    }
    Ok(())
}

fn conditions_hold(
    ctx: &ReducerContext,
    character: Identity,
    row: &QuestState,
    event: Event,
    level: u8,
    trigger: &Value,
) -> bool {
    if trigger["operator_only"].as_bool() == Some(true)
        && !crate::admin::is_operator(ctx, character)
    {
        return false;
    }
    if let Some(minimum) = trigger["level_min"].as_u64()
        && u64::from(level) < minimum
    {
        return false;
    }
    if let Some(maximum) = trigger["level_max"].as_u64()
        && u64::from(level) > maximum
    {
        return false;
    }
    if let Some(vnum) = trigger["vnum"].as_u64()
        && event.vnum().map(u64::from) != Some(vnum)
    {
        return false;
    }
    if let Some(vnum) = trigger["npc_vnum"].as_u64()
        && event.vnum().map(u64::from) != Some(vnum)
    {
        return false;
    }
    let tracker = tracker_for(ctx, character, row.quest_index);
    let amount = tracker.as_ref().map_or(0, |row| row.amount);
    if let Some(minimum) = trigger["objective_min"].as_u64()
        && u64::from(amount) < minimum
    {
        return false;
    }
    if let Some(maximum) = trigger["objective_max"].as_u64()
        && u64::from(amount) > maximum
    {
        return false;
    }
    if let Some(vnum) = trigger["item_vnum"].as_u64() {
        let vnum = u32::try_from(vnum).unwrap_or(0);
        let held = u64::from(inventory::owned_count(ctx, character, vnum));
        if let Some(minimum) = trigger["item_min"].as_u64()
            && held < minimum
        {
            return false;
        }
        if let Some(maximum) = trigger["item_max"].as_u64()
            && held > maximum
        {
            return false;
        }
    }
    true
}

fn tracker_rows(ctx: &ReducerContext, character: Identity) -> Vec<QuestObjective> {
    let mut rows: Vec<_> = ctx
        .db
        .quest_objective()
        .character_id()
        .filter(character)
        .collect();
    rows.sort_by_key(|row| row.id);
    rows
}

fn tracker_for(ctx: &ReducerContext, character: Identity, index: u16) -> Option<QuestObjective> {
    tracker_rows(ctx, character)
        .into_iter()
        .find(|row| row.quest_index == index)
}

fn write_tracker(ctx: &ReducerContext, row: QuestObjective) {
    if ctx.db.quest_objective().id().find(row.id).is_some() {
        ctx.db.quest_objective().id().update(row);
    } else {
        ctx.db.quest_objective().insert(row);
    }
}

/// Fetch the tracker entry for a quest, creating or adopting one as needed.
fn update_tracker(
    ctx: &ReducerContext,
    character: Identity,
    account: Identity,
    index: u16,
    update: impl FnOnce(&mut QuestObjective),
) {
    let mut row = tracker_for(ctx, character, index).unwrap_or_else(|| QuestObjective {
        id: next_tracker_id(ctx),
        character_id: character,
        account,
        quest_index: index,
        quest_id: quest_id(index).unwrap_or_default().to_owned(),
        letter_title: String::new(),
        label: String::new(),
        target_vnum: 0,
        amount: 0,
        total: 0,
        remaining_display: false,
        updated_at_us: 0,
    });
    update(&mut row);
    row.updated_at_us = now_us(ctx);
    let empty = row.letter_title.trim().is_empty()
        && row.label.trim().is_empty()
        && row.total == 0
        && row.amount == 0;
    if empty {
        ctx.db.quest_objective().id().delete(row.id);
        return;
    }
    write_tracker(ctx, row);
}

fn clear_tracker_progress(ctx: &ReducerContext, character: Identity, index: u16) {
    update_tracker(
        ctx,
        character,
        crate::accounts::owner_account(ctx, character).unwrap_or_default(),
        index,
        |row| {
            row.amount = 0;
            row.total = 0;
            row.remaining_display = false;
        },
    );
}

fn remove_tracker(ctx: &ReducerContext, character: Identity, index: u16) {
    for row in tracker_rows(ctx, character) {
        if row.quest_index == index {
            ctx.db.quest_objective().id().delete(row.id);
        }
    }
}

fn run_ops(
    ctx: &ReducerContext,
    character: Identity,
    index: u16,
    row: &mut QuestState,
    ops: &Value,
    outcome: &mut Outcome,
) -> Result<(), String> {
    // Trigger dialogue is what the player reads when the trigger itself is the
    // whole conversation. `drain_enters` replaces it only when the state this
    // trigger entered actually has lines of its own, so both cases work.
    let mut dialogue = std::mem::take(&mut outcome.dialogue);
    let result = run_ops_collecting(ctx, character, index, row, ops, outcome, &mut dialogue);
    outcome.dialogue = dialogue;
    result
}

/// Execute ops in order. `say`, `wait` and the `say_*` presentation ops
/// describe the conversation the client should render; every other op is an
/// authoritative mutation inside the caller's transaction.
fn run_ops_collecting(
    ctx: &ReducerContext,
    character: Identity,
    index: u16,
    row: &mut QuestState,
    ops: &Value,
    outcome: &mut Outcome,
    dialogue: &mut Dialogue,
) -> Result<(), String> {
    let Some(ops) = ops.as_array() else {
        return Err("Quest ops must be an array.".into());
    };
    // Text of a reward block whose item quantity is only known from the
    // following `say_reward_item` op.
    let mut pending_reward: Option<String> = None;
    for op in ops {
        match op["op"].as_str().unwrap_or_default() {
            "say" => {
                if dialogue.options.is_empty() {
                    if let Some(title) = op["title"].as_str() {
                        dialogue.set_title(title);
                    }
                    if let Some(body) = op["body"].as_str() {
                        dialogue.push(body);
                    }
                }
            }
            "wait" => {}
            "letter" => {
                let title = op["title"].as_str().unwrap_or_default().to_owned();
                update_tracker(ctx, character, row.account, index, |tracker| {
                    tracker.letter_title = clean(&title);
                });
                outcome.granted = true;
            }
            "clear_letter" => {
                update_tracker(ctx, character, row.account, index, |tracker| {
                    tracker.letter_title.clear();
                });
                outcome.granted = true;
            }
            "target" => {
                let label = op["label"].as_str().unwrap_or_default().to_owned();
                let vnum = u32::try_from(op["npc_vnum"].as_u64().unwrap_or(0)).unwrap_or(0);
                update_tracker(ctx, character, row.account, index, |tracker| {
                    tracker.label = clean(&label);
                    tracker.target_vnum = vnum;
                });
                outcome.granted = true;
            }
            "objective" => {
                let total = u32::try_from(op["total"].as_u64().unwrap_or(0)).unwrap_or(0);
                let label = op["label"].as_str().unwrap_or_default().to_owned();
                let remaining = op["display"].as_str() == Some("remaining");
                update_tracker(ctx, character, row.account, index, |tracker| {
                    if tracker.total != total {
                        tracker.amount = tracker.amount.min(total);
                    }
                    tracker.total = total;
                    tracker.remaining_display = remaining;
                    if !label.trim().is_empty() {
                        tracker.label = clean(&label);
                    }
                    tracker.target_vnum = 0;
                });
                outcome.granted = true;
            }
            "count" => {
                let total = u32::try_from(op["total"].as_u64().unwrap_or(0)).unwrap_or(0);
                let existing = tracker_for(ctx, character, index).map_or(0, |tracker| {
                    if tracker.total == total {
                        tracker.amount
                    } else {
                        tracker.amount.min(total)
                    }
                });
                let current = existing.saturating_add(1).min(total);
                update_tracker(ctx, character, row.account, index, |tracker| {
                    tracker.total = total;
                    tracker.amount = current;
                });
                outcome.granted = true;
                if current >= total && total > 0 {
                    run_ops_collecting(
                        ctx,
                        character,
                        index,
                        row,
                        &op["on_reached"],
                        outcome,
                        dialogue,
                    )?;
                }
            }
            "select" => {
                let options: Vec<String> = op["options"]
                    .as_array()
                    .map(|values| {
                        values
                            .iter()
                            .filter_map(|value| value.as_str().map(clean))
                            .collect()
                    })
                    .unwrap_or_default();
                let branches = op["branches"].clone();
                if options.is_empty() || branches.as_array().map_or(0, Vec::len) != options.len() {
                    return Err("Scripted question is malformed.".into());
                }
                dialogue.options = options.clone();
                let now = now_us(ctx);
                ctx.db.quest_selection().character_id().delete(character);
                ctx.db.quest_selection().insert(QuestSelection {
                    character_id: character,
                    account: row.account,
                    npc_vnum: outcome.npc_vnum,
                    quest_index: index,
                    options,
                    branches_json: branches.to_string(),
                    created_at_us: now,
                    expires_at_us: now.saturating_add(SELECTION_US),
                });
            }
            "set_state" => {
                let target = op["state"]
                    .as_str()
                    .ok_or("Quest op is missing its state.")?;
                if state_doc(index, target).is_none() {
                    return Err("Quest op targets an unknown state.".into());
                }
                if row.state == target {
                    continue;
                }
                row.state = target.to_owned();
                row.sequence = row.sequence.saturating_add(1);
                row.updated_at_us = now_us(ctx);
                ctx.db.quest_state().id().update(row.clone());
                if target == COMPLETE {
                    remove_tracker(ctx, character, index);
                }
                outcome.queue.push_back((index, target.to_owned()));
                outcome.granted = true;
            }
            "set_quest_state" => {
                let target_id = op["quest"].as_str().unwrap_or_default();
                let state = op["state"].as_str().unwrap_or_default();
                let Some(target_index) = quest_index(target_id) else {
                    continue;
                };
                if state_doc(target_index, state).is_none() {
                    // The compiler already rejects unknown states; a catalog
                    // from an older content revision simply does nothing.
                    continue;
                }
                let Some(mut other) = state_row_for(ctx, character, target_index) else {
                    continue;
                };
                if other.state == state || other.state == COMPLETE {
                    continue;
                }
                other.state = state.to_owned();
                other.sequence = other.sequence.saturating_add(1);
                other.updated_at_us = now_us(ctx);
                ctx.db.quest_state().id().update(other.clone());
                if target_index == index {
                    *row = other;
                }
                if state == COMPLETE {
                    remove_tracker(ctx, character, target_index);
                }
                outcome.queue.push_back((target_index, state.to_owned()));
                outcome.granted = true;
            }
            "give_exp" => {
                let amount = op["amount"].as_u64().unwrap_or(0);
                if amount > 0 {
                    progression::apply_exact_experience(ctx, character, amount)?;
                    outcome.granted = true;
                }
            }
            "give_money" => {
                let amount = u32::try_from(op["amount"].as_u64().unwrap_or(0))
                    .map_err(|_| "Invalid Yang reward.".to_string())?;
                if amount > 0 {
                    let mut player = ctx
                        .db
                        .player()
                        .identity()
                        .find(character)
                        .ok_or("Enter the world before claiming a reward.")?;
                    player.gold = player
                        .gold
                        .checked_add(amount)
                        .ok_or("Yang limit reached.")?;
                    ctx.db.player().identity().update(player);
                    outcome.granted = true;
                }
            }
            "give_item" => {
                let vnum = u32::try_from(op["vnum"].as_u64().unwrap_or(0)).unwrap_or(0);
                let count = u16::try_from(op["count"].as_u64().unwrap_or(0))
                    .map_err(|_| "Invalid item quantity.".to_string())?;
                item_catalog::definition(vnum)
                    .map_err(|_| format!("Quest reward item {vnum} is not installed."))?;
                inventory::grant(ctx, character, vnum, count, Cause::Quest)?;
                outcome.granted = true;
            }
            "remove_item" => {
                let vnum = u32::try_from(op["vnum"].as_u64().unwrap_or(0)).unwrap_or(0);
                let count = u32::try_from(op["count"].as_u64().unwrap_or(0)).unwrap_or(0);
                inventory::consume_owned(ctx, character, vnum, count)?;
                outcome.granted = true;
            }
            "random_item" => {
                let choices: Vec<u32> = op["choices"]
                    .as_array()
                    .map(|values| {
                        values
                            .iter()
                            .filter_map(|value| u32::try_from(value.as_u64()?).ok())
                            .collect()
                    })
                    .unwrap_or_default();
                if choices.is_empty() {
                    return Err("Random quest reward has no choices.".into());
                }
                for vnum in &choices {
                    item_catalog::definition(*vnum)
                        .map_err(|_| format!("Quest reward item {vnum} is not installed."))?;
                }
                let count = u16::try_from(op["count"].as_u64().unwrap_or(1))
                    .map_err(|_| "Invalid item quantity.".to_string())?;
                let pick = choices[ctx.rng().gen_range(0..choices.len())];
                inventory::grant(ctx, character, pick, count, Cause::Quest)?;
                outcome.granted = true;
            }
            "say_reward" => {
                let text = op["text"].as_str().unwrap_or_default();
                match dialogue.reward_item {
                    Some((vnum, count)) => {
                        let rendered =
                            fill_placeholders(text, &[item_name(vnum), count.to_string()]);
                        dialogue.push_reward(rendered);
                    }
                    None if has_placeholder(text) => pending_reward = Some(text.to_owned()),
                    None => dialogue.push(text),
                }
            }
            // Original `say_reward(string.format(KEY, amount))` lines print a
            // grant the quest already applied with a separate op. The amount is
            // stored beside the text instead of being re-derived from a reward
            // item, so a value line never claims a reward it does not grant.
            "say_reward_value" => {
                let text = op["text"].as_str().unwrap_or_default();
                let amount = op["amount"].as_u64().unwrap_or(0);
                dialogue.push_reward(fill_placeholders(text, &[amount.to_string()]));
            }
            "say_reward_item" => {
                let text = op["text"].as_str().unwrap_or_default();
                let vnum = u32::try_from(op["vnum"].as_u64().unwrap_or(0)).unwrap_or(0);
                let count = u32::try_from(op["count"].as_u64().unwrap_or(0)).unwrap_or(0);
                let rendered = fill_placeholders(text, &[item_name(vnum), count.to_string()]);
                dialogue.reward_item = Some((vnum, count));
                pending_reward = None;
                dialogue.push_reward(rendered);
            }
            "say_item" => {
                let text = op["text"].as_str().unwrap_or_default();
                let vnum = u32::try_from(op["vnum"].as_u64().unwrap_or(0)).unwrap_or(0);
                let rendered = match dialogue.reward_item {
                    Some((offered, count)) if offered == vnum => {
                        fill_placeholders(text, &[item_name(vnum), count.to_string()])
                    }
                    _ => fill_placeholders(text, &[item_name(vnum)]),
                };
                dialogue.push_reward(rendered);
            }
            "say_reward_counter" => {
                let text = op["text"].as_str().unwrap_or_default();
                let amount = tracker_for(ctx, character, index).map_or(0, |tracker| {
                    if tracker.remaining_display {
                        tracker.total.saturating_sub(tracker.amount)
                    } else {
                        tracker.amount
                    }
                });
                dialogue.push(&fill_placeholders(text, &[amount.to_string()]));
            }
            other => return Err(format!("Unsupported quest operation: {other}")),
        }
    }
    if let Some(text) = pending_reward {
        // A reward block without an item op keeps its prose, with the
        // placeholders removed so the client never shows `%s`.
        dialogue.push(&fill_placeholders(&text, &[]));
    }
    Ok(())
}

/// Resolve an item's display name, falling back to its vnum.
fn item_name(vnum: u32) -> String {
    item_catalog::name(vnum).map_or_else(|| format!("Item {vnum}"), str::to_owned)
}

/// `[ENTER]` is the original client's line-break token; trailing spaces come
/// from the extracted localization strings.
fn clean(text: &str) -> String {
    text.replace("[ENTER]", "\n")
        .lines()
        .map(str::trim_end)
        .collect::<Vec<_>>()
        .join("\n")
        .trim()
        .to_owned()
}

/// Same normalization as [`clean`], exposed so the NPC session can bound the
/// text it stores without duplicating the original client's line-break rules.
pub fn clean_line(text: &str) -> String {
    clean(text)
}

/// Fill `%s` placeholders left to right; extra placeholders are dropped.
/// True when a line still needs an argument before it can be shown.
fn has_placeholder(text: &str) -> bool {
    ["%s", "%d"].iter().any(|token| text.contains(token))
}

/// Substitute the placeholders the original locale strings use.
///
/// The pinned English translations mix `%s` and `%d` for the same positional
/// argument, so one ordered pass fills either spelling from the same argument
/// list and leaves an excess token unsubstituted rather than reordering lines.
fn fill_placeholders(text: &str, arguments: &[String]) -> String {
    let mut rendered = String::with_capacity(text.len());
    let mut used = 0usize;
    let mut rest = text;
    while let Some((position, width)) = ["%s", "%d"]
        .iter()
        .filter_map(|token| rest.find(token).map(|position| (position, token.len())))
        .min_by_key(|(position, _)| *position)
    {
        rendered.push_str(&rest[..position]);
        if let Some(argument) = arguments.get(used) {
            rendered.push_str(argument);
        }
        used += 1;
        rest = &rest[position + width..];
    }
    rendered.push_str(rest);
    clean(&rendered)
}

/// Drop session-only quest UI state (a pending answer) while keeping progress,
/// letters and objectives so the tracker survives a reconnect.
pub fn suspend(ctx: &ReducerContext, character: Identity) {
    ctx.db.quest_selection().character_id().delete(character);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compiled_catalog_is_structurally_valid() {
        validate_content();
        if !definitions::QUEST_CATALOG.trim().is_empty() {
            assert!(!definitions::QUEST_CATALOG_HASH.is_empty());
            assert!(!order().is_empty());
        }
    }

    #[test]
    fn placeholders_fill_left_to_right_and_drop_the_rest() {
        let arguments = vec!["Red Potion".to_owned(), "15".to_owned()];
        assert_eq!(
            fill_placeholders("Item: %s, Quantity: %s ", &arguments),
            "Item: Red Potion, Quantity: 15"
        );
        assert_eq!(
            fill_placeholders("Item: %s, Quantity: %s ", &[]),
            "Item: , Quantity:"
        );
        assert_eq!(
            fill_placeholders("Manufacturing armour ", &[]),
            "Manufacturing armour"
        );
    }

    #[test]
    fn enter_markers_become_line_breaks() {
        assert_eq!(clean("One[ENTER]Two[ENTER]Three "), "One\nTwo\nThree");
    }

    /// The first main quest has no `run` state. Character creation must still
    /// pick a state that its first login trigger can match, otherwise the quest
    /// silently never starts.
    #[test]
    fn every_quest_starts_in_a_state_it_can_leave() {
        for (position, entry) in order().iter().enumerate() {
            let index = u16::try_from(position).expect("quest catalog fits u16");
            let id = entry.as_str().expect("quest order entries must be names");
            let state = initial_state(index);
            let Some(document) = state_doc(index, &state) else {
                panic!("quest {id} initial state {state} must exist");
            };
            let triggers = document["triggers"]
                .as_array()
                .unwrap_or_else(|| panic!("quest {id}.{state} triggers must be an array"));
            for trigger in triggers {
                let event = trigger["event"].as_str().unwrap_or_default().to_owned();
                assert!(
                    ["login", "levelup", "kill", "npc_click", "npc_chat"].contains(&event.as_str()),
                    "quest {id}.{state} has an unknown trigger event {event}"
                );
            }
        }
    }

    /// A character must be able to finish every compiled quest, so each one has
    /// to declare the terminal state the runtime compares against.
    #[test]
    fn every_quest_declares_its_terminal_state() {
        for entry in order() {
            let id = entry.as_str().expect("quest order entries must be names");
            assert!(
                catalog()["quests"][id]["states"][COMPLETE].is_object(),
                "quest {id} needs a {COMPLETE} state"
            );
        }
    }

    /// Clicking the City Guard enters `find_squareguard`, whose `enter` says
    /// where to go next. That notice must not replace the guard's own two
    /// lines, but a transition with no interaction behind it still needs to
    /// reach the panel.
    #[test]
    fn interaction_text_outranks_a_reached_state_notice() {
        let mut click = Outcome::default();
        click.dialogue.push("You must be new in town!");
        click.notice.push("Go to the centre of the village.");
        let shown = presented(click);
        assert_eq!(shown.body(), "You must be new in town!");

        let mut transition = Outcome::default();
        transition.notice.set_title("Welcome to Metin2 ");
        transition.notice.push("Find the City Guard.");
        let shown = presented(transition);
        assert_eq!(shown.title, "Welcome to Metin2");
        assert_eq!(shown.body(), "Find the City Guard.");
    }

    #[test]
    fn notices_from_several_states_keep_the_first_title() {
        let mut notice = Dialogue::default();
        let mut first = Dialogue::default();
        first.set_title("Information: ");
        first.push("Go to the centre of the village.");
        let mut second = Dialogue::default();
        second.set_title("Welcome to Metin2 ");
        second.push("Find the City Guard.");
        second.options.push("Yes".to_owned());
        notice.absorb(first);
        notice.absorb(second);
        assert_eq!(notice.title, "Information:");
        assert_eq!(
            notice.body(),
            "Go to the centre of the village.\nFind the City Guard."
        );
        assert_eq!(notice.options, vec!["Yes".to_owned()]);
    }
}
