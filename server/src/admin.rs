//! Narrow, audited progression administration for authenticated account operators.
//!
//! This module deliberately exposes dedicated reducers rather than a generic command
//! interpreter. Authorization is keyed only by the authenticated account identity.

use crate::accounts::{self, AccountState, account_state};
use crate::now_us;
use crate::progression::{
    self, AutomaticItemSummary, LevelRoll, ProgressionOutcome, ProgressionSnapshot,
};
use spacetimedb::{ConnectionId, Filter, Identity, ReducerContext, Table, Timestamp};

const PROTOCOL_VERSION: u32 = 6;
const RATE_INTERVAL_US: i64 = 1_000_000;
const FEEDBACK_LIMIT: usize = 32;
const REQUEST_ID_LEN: usize = 32;
const MAX_NUMERIC_INPUT_BYTES: usize = 64;
const MAX_REASON_CHARS: usize = 160;

#[spacetimedb::table(accessor = command_feedback, public)]
#[derive(Clone)]
pub struct CommandFeedback {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    #[index(btree)]
    pub account: Identity,
    #[index(btree)]
    pub request_id: String,
    pub severity: String,
    pub message: String,
    pub created_at: Timestamp,
}

#[spacetimedb::client_visibility_filter]
const OWN_COMMAND_FEEDBACK: Filter =
    Filter::Sql("SELECT * FROM command_feedback WHERE command_feedback.account = :sender");

#[spacetimedb::table(accessor = progression_operator)]
pub struct ProgressionOperator {
    #[primary_key]
    pub account: Identity,
    pub enabled: bool,
    pub changed_by: Identity,
    pub changed_at: Timestamp,
    pub audit_id: u64,
}

#[spacetimedb::table(accessor = admin_rate)]
pub struct AdminRate {
    #[primary_key]
    pub account: Identity,
    pub next_progression_us: i64,
    pub next_help_us: i64,
}

#[spacetimedb::table(accessor = admin_request_receipt)]
#[derive(Clone)]
pub struct AdminRequestReceipt {
    #[primary_key]
    pub request_id: String,
    pub actor_account: Identity,
    pub action: String,
    pub canonical_argument: String,
    pub target_account: Identity,
    pub target_character: Identity,
    pub outcome: String,
    pub reason_code: String,
    pub severity: String,
    pub message: String,
    pub created_at: Timestamp,
    pub audit_id: u64,
    pub applied_experience: u64,
}

#[spacetimedb::table(accessor = admin_request_collision)]
pub struct AdminRequestCollision {
    #[primary_key]
    pub collision_key: String,
    pub request_id: String,
    pub actor_account: Identity,
    pub audit_id: u64,
}

#[derive(spacetimedb::SpacetimeType, Clone)]
pub struct AdminLevelRoll {
    pub resulting_level: u8,
    pub hp: u32,
    pub sp: u32,
}

#[spacetimedb::table(accessor = admin_audit)]
pub struct AdminAudit {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    pub request_id: String,
    pub created_at: Timestamp,
    pub protocol_version: u32,
    pub definition_hash: String,
    #[index(btree)]
    pub actor_account: Identity,
    pub target_account: Identity,
    pub target_character: Identity,
    pub connection_id: ConnectionId,
    pub action: String,
    pub canonical_argument: String,
    pub reason: String,
    pub outcome: String,
    pub reason_code: String,
    pub has_progression: bool,
    pub before_level: u8,
    pub before_experience: u32,
    pub before_level_step: u8,
    pub before_unspent_stat_points: u16,
    pub before_random_hp: u32,
    pub before_random_sp: u32,
    pub before_health: u16,
    pub before_max_health: u16,
    pub before_current_sp: u32,
    pub before_max_sp: u32,
    pub after_level: u8,
    pub after_experience: u32,
    pub after_level_step: u8,
    pub after_unspent_stat_points: u16,
    pub after_random_hp: u32,
    pub after_random_sp: u32,
    pub after_health: u16,
    pub after_max_health: u16,
    pub after_current_sp: u32,
    pub after_max_sp: u32,
    pub applied_experience: u64,
    pub level_rolls: Vec<AdminLevelRoll>,
    pub small_potions: u16,
    pub medium_potions: u16,
    pub stacked_items: u16,
    pub inserted_items: u16,
    pub dropped_items: u16,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Action {
    Help,
    XpGrant,
    LevelRaise,
    OperatorGrant,
    OperatorRevoke,
}

impl Action {
    fn id(self) -> &'static str {
        match self {
            Self::Help => "help",
            Self::XpGrant => "xp_grant",
            Self::LevelRaise => "level_raise",
            Self::OperatorGrant => "operator_grant",
            Self::OperatorRevoke => "operator_revoke",
        }
    }

    fn uses_help_rate(self) -> bool {
        self == Self::Help
    }
}

struct Attempt<'a> {
    request_id: &'a str,
    action: Action,
    canonical_argument: &'a str,
    target_account: Identity,
    target_character: Identity,
    outcome: &'a str,
    reason_code: &'a str,
    severity: &'a str,
    message: &'a str,
    reason: &'a str,
    progression: Option<&'a ProgressionOutcome>,
}

struct Denial<'a> {
    request_id: &'a str,
    action: Action,
    canonical_argument: &'a str,
    reason_code: &'a str,
    message: &'a str,
    target_character: Identity,
    reason: &'a str,
}

struct ProgressionSuccess<'a> {
    request_id: &'a str,
    action: Action,
    canonical_argument: &'a str,
    target_character: Identity,
    message: &'a str,
    outcome: &'a ProgressionOutcome,
}

/// Validate deployment roots during database initialization. Invalid configuration
/// aborts initialization without echoing the configured identity value to host logs.
pub fn initialize() {
    for (index, value) in crate::definitions::PROGRESSION_BOOTSTRAP_IDENTITIES
        .iter()
        .enumerate()
    {
        if canonical_identity(value).is_none() {
            panic!("compiled progression bootstrap identity {index} is invalid");
        }
    }
}

#[spacetimedb::reducer]
pub fn request_command_help(ctx: &ReducerContext, request_id: String) -> Result<(), String> {
    let (account, connection_id) = accounts::authenticated_controlled_account(ctx)?;
    let request_id =
        match admit_request(ctx, &account, connection_id, Action::Help, &request_id, "")? {
            Admission::Replay => return Ok(()),
            Admission::New(value) => value,
            Admission::RateLimited => return Ok(()),
        };
    if request_id.is_empty() {
        return finish_denial(
            ctx,
            &account,
            connection_id,
            Denial {
                request_id: "",
                action: Action::Help,
                canonical_argument: "",
                reason_code: "invalid_request_id",
                message: "Use a valid command request identifier.",
                target_character: Identity::ZERO,
                reason: "",
            },
        );
    }
    let message = if has_progression_capability(ctx, account.account) {
        "Commands: /help, /xp <1..4294967295>, /level <2..99>."
    } else {
        "Commands: /help. Type a normal message without a leading slash to chat."
    };
    finish_attempt(
        ctx,
        account.account,
        connection_id,
        Attempt {
            request_id: &request_id,
            action: Action::Help,
            canonical_argument: "",
            target_account: Identity::ZERO,
            target_character: Identity::ZERO,
            outcome: "applied",
            reason_code: "help",
            severity: "info",
            message,
            reason: "",
            progression: None,
        },
    );
    Ok(())
}

#[spacetimedb::reducer]
pub fn admin_grant_progression_xp(
    ctx: &ReducerContext,
    request_id: String,
    amount_text: String,
) -> Result<(), String> {
    let (account, connection_id) = accounts::authenticated_controlled_account(ctx)?;
    let canonical = canonical_numeric_intent(&amount_text);
    let request_id = match admit_request(
        ctx,
        &account,
        connection_id,
        Action::XpGrant,
        &request_id,
        &canonical,
    )? {
        Admission::Replay => return Ok(()),
        Admission::New(value) => value,
        Admission::RateLimited => return Ok(()),
    };
    let target = account.selected_character;
    if request_id.is_empty() {
        return finish_denial(
            ctx,
            &account,
            connection_id,
            Denial {
                request_id: "",
                action: Action::XpGrant,
                canonical_argument: &canonical,
                reason_code: "invalid_request_id",
                message: "Use a valid command request identifier.",
                target_character: target,
                reason: "",
            },
        );
    }
    if !has_progression_capability(ctx, account.account) {
        return finish_denial(
            ctx,
            &account,
            connection_id,
            Denial {
                request_id: &request_id,
                action: Action::XpGrant,
                canonical_argument: &canonical,
                reason_code: "permission",
                message: "This account lacks progression-admin access.",
                target_character: target,
                reason: "",
            },
        );
    }
    let amount = match parse_positive_u32(&amount_text) {
        Ok(value) => value,
        Err(()) => {
            return finish_denial(
                ctx,
                &account,
                connection_id,
                Denial {
                    request_id: &request_id,
                    action: Action::XpGrant,
                    canonical_argument: &canonical,
                    reason_code: "invalid_xp",
                    message: "Usage: /xp <1..4294967295>.",
                    target_character: target,
                    reason: "",
                },
            );
        }
    };
    let (character, progression_row) = match progression::selected_supported_progression(ctx) {
        Ok(value) => value,
        Err(_) => {
            return finish_denial(
                ctx,
                &account,
                connection_id,
                Denial {
                    request_id: &request_id,
                    action: Action::XpGrant,
                    canonical_argument: &canonical,
                    reason_code: "character_unavailable",
                    message: "Enter the selected supported character first.",
                    target_character: target,
                    reason: "",
                },
            );
        }
    };
    let capacity = progression::remaining_experience_capacity(&progression_row)?;
    if u64::from(amount) > capacity {
        return finish_denial(
            ctx,
            &account,
            connection_id,
            Denial {
                request_id: &request_id,
                action: Action::XpGrant,
                canonical_argument: &canonical,
                reason_code: "xp_over_capacity",
                message: "That XP amount exceeds the character's remaining capacity.",
                target_character: character,
                reason: "",
            },
        );
    }
    let outcome = progression::apply_exact_experience(ctx, character, u64::from(amount))?;
    finish_progression_success(
        ctx,
        &account,
        connection_id,
        ProgressionSuccess {
            request_id: &request_id,
            action: Action::XpGrant,
            canonical_argument: &amount.to_string(),
            target_character: character,
            message: &format!(
                "Applied exactly {} progression XP with normal rewards.",
                amount
            ),
            outcome: &outcome,
        },
    );
    Ok(())
}

#[spacetimedb::reducer]
pub fn admin_raise_progression_level(
    ctx: &ReducerContext,
    request_id: String,
    target_text: String,
) -> Result<(), String> {
    let (account, connection_id) = accounts::authenticated_controlled_account(ctx)?;
    let canonical = canonical_numeric_intent(&target_text);
    let request_id = match admit_request(
        ctx,
        &account,
        connection_id,
        Action::LevelRaise,
        &request_id,
        &canonical,
    )? {
        Admission::Replay => return Ok(()),
        Admission::New(value) => value,
        Admission::RateLimited => return Ok(()),
    };
    let selected = account.selected_character;
    if request_id.is_empty() {
        return finish_denial(
            ctx,
            &account,
            connection_id,
            Denial {
                request_id: "",
                action: Action::LevelRaise,
                canonical_argument: &canonical,
                reason_code: "invalid_request_id",
                message: "Use a valid command request identifier.",
                target_character: selected,
                reason: "",
            },
        );
    }
    if !has_progression_capability(ctx, account.account) {
        return finish_denial(
            ctx,
            &account,
            connection_id,
            Denial {
                request_id: &request_id,
                action: Action::LevelRaise,
                canonical_argument: &canonical,
                reason_code: "permission",
                message: "This account lacks progression-admin access.",
                target_character: selected,
                reason: "",
            },
        );
    }
    let target = match parse_positive_u32(&target_text) {
        Ok(value) if (2..=99).contains(&value) => value as u8,
        _ => {
            return finish_denial(
                ctx,
                &account,
                connection_id,
                Denial {
                    request_id: &request_id,
                    action: Action::LevelRaise,
                    canonical_argument: &canonical,
                    reason_code: "invalid_level",
                    message: "Usage: /level <2..99>; the target must exceed the current level.",
                    target_character: selected,
                    reason: "",
                },
            );
        }
    };
    let (character, progression_row) = match progression::selected_supported_progression(ctx) {
        Ok(value) => value,
        Err(_) => {
            return finish_denial(
                ctx,
                &account,
                connection_id,
                Denial {
                    request_id: &request_id,
                    action: Action::LevelRaise,
                    canonical_argument: &canonical,
                    reason_code: "character_unavailable",
                    message: "Enter the selected supported character first.",
                    target_character: selected,
                    reason: "",
                },
            );
        }
    };
    if target <= progression_row.level {
        return finish_denial(
            ctx,
            &account,
            connection_id,
            Denial {
                request_id: &request_id,
                action: Action::LevelRaise,
                canonical_argument: &canonical,
                reason_code: "level_not_higher",
                message: "The target level must exceed the current level.",
                target_character: character,
                reason: "",
            },
        );
    }
    let amount = progression::experience_to_reach_level(&progression_row, target)?;
    let outcome = progression::apply_exact_experience(ctx, character, amount)?;
    if outcome.after.level != target
        || outcome.after.experience != 0
        || outcome.after.level_step != 0
    {
        return Err("Progression level planning produced an inconsistent result.".into());
    }
    finish_progression_success(
        ctx,
        &account,
        connection_id,
        ProgressionSuccess {
            request_id: &request_id,
            action: Action::LevelRaise,
            canonical_argument: &target.to_string(),
            target_character: character,
            message: &format!(
                "Raised level {} to {} through normal progression rewards.",
                outcome.before.level, target
            ),
            outcome: &outcome,
        },
    );
    Ok(())
}

#[spacetimedb::reducer]
pub fn provision_progression_operator(
    ctx: &ReducerContext,
    request_id: String,
    target_account: Identity,
    enabled: bool,
    reason: String,
) -> Result<(), String> {
    let (account, connection_id) = accounts::authenticated_controlled_account(ctx)?;
    let normalized_reason = normalize_reason(&reason);
    let canonical = canonical_provision_intent(
        target_account,
        enabled,
        &reason,
        normalized_reason.as_deref(),
    );
    let action = if enabled {
        Action::OperatorGrant
    } else {
        Action::OperatorRevoke
    };
    let request_id = match admit_request(
        ctx,
        &account,
        connection_id,
        action,
        &request_id,
        &canonical,
    )? {
        Admission::Replay => return Ok(()),
        Admission::New(value) => value,
        Admission::RateLimited => return Ok(()),
    };
    if request_id.is_empty() {
        return finish_denial(
            ctx,
            &account,
            connection_id,
            Denial {
                request_id: "",
                action,
                canonical_argument: &canonical,
                reason_code: "invalid_request_id",
                message: "Use a valid command request identifier.",
                target_character: Identity::ZERO,
                reason: "",
            },
        );
    }
    if !is_bootstrap_identity(account.account) {
        return finish_denial(
            ctx,
            &account,
            connection_id,
            Denial {
                request_id: &request_id,
                action,
                canonical_argument: &canonical,
                reason_code: "bootstrap_required",
                message: "Only a configured bootstrap operator can change progression-admin access.",
                target_character: Identity::ZERO,
                reason: "",
            },
        );
    }
    let Some(reason) = normalized_reason else {
        return finish_denial(
            ctx,
            &account,
            connection_id,
            Denial {
                request_id: &request_id,
                action,
                canonical_argument: &canonical,
                reason_code: "invalid_reason",
                message: "Reason must be 3 to 160 printable characters.",
                target_character: Identity::ZERO,
                reason: "",
            },
        );
    };
    if ctx
        .db
        .account_state()
        .account()
        .find(target_account)
        .is_none()
    {
        return finish_denial(
            ctx,
            &account,
            connection_id,
            Denial {
                request_id: &request_id,
                action,
                canonical_argument: &canonical,
                reason_code: "unknown_target_account",
                message: "The exact target account identity has not opened this game database.",
                target_character: Identity::ZERO,
                reason: &reason,
            },
        );
    }
    if !enabled && is_bootstrap_identity(target_account) {
        return finish_denial(
            ctx,
            &account,
            connection_id,
            Denial {
                request_id: &request_id,
                action,
                canonical_argument: &canonical,
                reason_code: "bootstrap_is_configured",
                message: "A configured bootstrap identity can only be removed by republishing configuration.",
                target_character: Identity::ZERO,
                reason: &reason,
            },
        );
    }

    let attempt = Attempt {
        request_id: &request_id,
        action,
        canonical_argument: &canonical,
        target_account,
        target_character: Identity::ZERO,
        outcome: "applied",
        reason_code: if enabled {
            "operator_enabled"
        } else {
            "operator_disabled"
        },
        severity: "success",
        message: if enabled {
            "Progression-admin access enabled."
        } else {
            "Progression-admin access revoked."
        },
        reason: &reason,
        progression: None,
    };
    let audit = insert_audit(ctx, account.account, connection_id, &attempt);
    let row = ProgressionOperator {
        account: target_account,
        enabled,
        changed_by: account.account,
        changed_at: ctx.timestamp,
        audit_id: audit.id,
    };
    if ctx
        .db
        .progression_operator()
        .account()
        .find(target_account)
        .is_some()
    {
        ctx.db.progression_operator().account().update(row);
    } else {
        ctx.db.progression_operator().insert(row);
    }
    insert_receipt_and_feedback(
        ctx,
        account.account,
        &audit,
        if enabled {
            "Progression-admin access enabled."
        } else {
            "Progression-admin access revoked."
        },
        "success",
        0,
    );
    Ok(())
}

enum Admission {
    Replay,
    New(String),
    RateLimited,
}

fn admit_request(
    ctx: &ReducerContext,
    account: &AccountState,
    connection_id: ConnectionId,
    action: Action,
    raw_request_id: &str,
    canonical_argument: &str,
) -> Result<Admission, String> {
    if valid_request_id(raw_request_id)
        && let Some(receipt) = ctx
            .db
            .admin_request_receipt()
            .request_id()
            .find(raw_request_id.to_string())
    {
        if receipt.actor_account == account.account {
            if receipt.action == action.id() && receipt.canonical_argument == canonical_argument {
                upsert_feedback(
                    ctx,
                    account.account,
                    raw_request_id,
                    &receipt.severity,
                    &receipt.message,
                );
                return Ok(Admission::Replay);
            }
            let conflict_key = format!("{}:{raw_request_id}:mismatch", account.account);
            if ctx
                .db
                .admin_request_collision()
                .collision_key()
                .find(&conflict_key)
                .is_some()
            {
                upsert_feedback(
                    ctx,
                    account.account,
                    raw_request_id,
                    "error",
                    "That request identifier is already bound to different arguments.",
                );
                return Ok(Admission::Replay);
            }
            if !reserve_rate(ctx, account.account, action) {
                rate_feedback(ctx, account.account);
                return Ok(Admission::RateLimited);
            }
            let attempt = Attempt {
                request_id: raw_request_id,
                action,
                canonical_argument: "receipt_mismatch",
                target_account: receipt.target_account,
                target_character: receipt.target_character,
                outcome: "duplicate",
                reason_code: "request_id_argument_mismatch",
                severity: "error",
                message: "That request identifier is already bound to different arguments.",
                reason: "",
                progression: None,
            };
            let audit = insert_audit(ctx, account.account, connection_id, &attempt);
            ctx.db
                .admin_request_collision()
                .insert(AdminRequestCollision {
                    collision_key: conflict_key,
                    request_id: raw_request_id.into(),
                    actor_account: account.account,
                    audit_id: audit.id,
                });
            upsert_feedback(
                ctx,
                account.account,
                raw_request_id,
                "error",
                "That request identifier is already bound to different arguments.",
            );
            return Ok(Admission::Replay);
        }
        let collision_key = format!("{}:{raw_request_id}:foreign", account.account);
        if ctx
            .db
            .admin_request_collision()
            .collision_key()
            .find(&collision_key)
            .is_some()
        {
            upsert_feedback(
                ctx,
                account.account,
                raw_request_id,
                "error",
                "That request identifier belongs to another account.",
            );
            return Ok(Admission::Replay);
        }
        if !reserve_rate(ctx, account.account, action) {
            rate_feedback(ctx, account.account);
            return Ok(Admission::RateLimited);
        }
        let attempt = Attempt {
            request_id: raw_request_id,
            action,
            canonical_argument,
            target_account: Identity::ZERO,
            target_character: account.selected_character,
            outcome: "duplicate",
            reason_code: "request_id_owned_by_other_account",
            severity: "error",
            message: "That request identifier belongs to another account.",
            reason: "",
            progression: None,
        };
        let audit = insert_audit(ctx, account.account, connection_id, &attempt);
        ctx.db
            .admin_request_collision()
            .insert(AdminRequestCollision {
                collision_key,
                request_id: raw_request_id.into(),
                actor_account: account.account,
                audit_id: audit.id,
            });
        upsert_feedback(
            ctx,
            account.account,
            raw_request_id,
            "error",
            "That request identifier belongs to another account.",
        );
        return Ok(Admission::Replay);
    }

    if !reserve_rate(ctx, account.account, action) {
        rate_feedback(ctx, account.account);
        return Ok(Admission::RateLimited);
    }
    Ok(Admission::New(if valid_request_id(raw_request_id) {
        raw_request_id.into()
    } else {
        String::new()
    }))
}

fn reserve_rate(ctx: &ReducerContext, account: Identity, action: Action) -> bool {
    let now = now_us(ctx);
    let mut row = ctx
        .db
        .admin_rate()
        .account()
        .find(account)
        .unwrap_or(AdminRate {
            account,
            next_progression_us: 0,
            next_help_us: 0,
        });
    let next = if action.uses_help_rate() {
        row.next_help_us
    } else {
        row.next_progression_us
    };
    if now < next {
        return false;
    }
    if action.uses_help_rate() {
        row.next_help_us = now.saturating_add(RATE_INTERVAL_US);
    } else {
        row.next_progression_us = now.saturating_add(RATE_INTERVAL_US);
    }
    if ctx.db.admin_rate().account().find(account).is_some() {
        ctx.db.admin_rate().account().update(row);
    } else {
        ctx.db.admin_rate().insert(row);
    }
    true
}

fn rate_feedback(ctx: &ReducerContext, account: Identity) {
    upsert_feedback(
        ctx,
        account,
        "",
        "warning",
        "Wait one second before another command request.",
    );
}

fn finish_denial(
    ctx: &ReducerContext,
    account: &AccountState,
    connection_id: ConnectionId,
    denial: Denial<'_>,
) -> Result<(), String> {
    let attempt = Attempt {
        request_id: denial.request_id,
        action: denial.action,
        canonical_argument: denial.canonical_argument,
        target_account: Identity::ZERO,
        target_character: denial.target_character,
        outcome: if matches!(denial.reason_code, "permission" | "bootstrap_required") {
            "denied_permission"
        } else {
            "denied_validation"
        },
        reason_code: denial.reason_code,
        severity: "error",
        message: denial.message,
        reason: denial.reason,
        progression: None,
    };
    finish_attempt(ctx, account.account, connection_id, attempt);
    Ok(())
}

fn finish_progression_success(
    ctx: &ReducerContext,
    account: &AccountState,
    connection_id: ConnectionId,
    success: ProgressionSuccess<'_>,
) {
    finish_attempt(
        ctx,
        account.account,
        connection_id,
        Attempt {
            request_id: success.request_id,
            action: success.action,
            canonical_argument: success.canonical_argument,
            target_account: Identity::ZERO,
            target_character: success.target_character,
            outcome: "applied",
            reason_code: "progression_applied",
            severity: "success",
            message: success.message,
            reason: "",
            progression: Some(success.outcome),
        },
    );
}

fn finish_attempt(
    ctx: &ReducerContext,
    actor: Identity,
    connection_id: ConnectionId,
    attempt: Attempt<'_>,
) {
    let message = attempt.message.to_string();
    let severity = attempt.severity.to_string();
    let applied = attempt
        .progression
        .map_or(0, |outcome| outcome.applied_experience);
    let audit = insert_audit(ctx, actor, connection_id, &attempt);
    if audit.request_id.is_empty() {
        upsert_feedback(ctx, actor, "", &severity, &message);
    } else {
        insert_receipt_and_feedback(ctx, actor, &audit, &message, &severity, applied);
    }
}

fn insert_audit(
    ctx: &ReducerContext,
    actor: Identity,
    connection_id: ConnectionId,
    attempt: &Attempt<'_>,
) -> AdminAudit {
    let (before, after, rolls, items, applied) = match attempt.progression {
        Some(value) => (
            Some(value.before),
            Some(value.after),
            value.level_rolls.iter().map(copy_roll).collect(),
            value.automatic_items,
            value.applied_experience,
        ),
        None => (None, None, Vec::new(), empty_items(), 0),
    };
    let before = before.unwrap_or_else(empty_snapshot);
    let after = after.unwrap_or_else(empty_snapshot);
    ctx.db.admin_audit().insert(AdminAudit {
        id: 0,
        request_id: attempt.request_id.into(),
        created_at: ctx.timestamp,
        protocol_version: PROTOCOL_VERSION,
        definition_hash: crate::definitions::DEFINITION_HASH.into(),
        actor_account: actor,
        target_account: attempt.target_account,
        target_character: attempt.target_character,
        connection_id,
        action: attempt.action.id().into(),
        canonical_argument: attempt.canonical_argument.into(),
        reason: attempt.reason.into(),
        outcome: attempt.outcome.into(),
        reason_code: attempt.reason_code.into(),
        has_progression: attempt.progression.is_some(),
        before_level: before.level,
        before_experience: before.experience,
        before_level_step: before.level_step,
        before_unspent_stat_points: before.unspent_stat_points,
        before_random_hp: before.random_hp,
        before_random_sp: before.random_sp,
        before_health: before.health,
        before_max_health: before.max_health,
        before_current_sp: before.current_sp,
        before_max_sp: before.max_sp,
        after_level: after.level,
        after_experience: after.experience,
        after_level_step: after.level_step,
        after_unspent_stat_points: after.unspent_stat_points,
        after_random_hp: after.random_hp,
        after_random_sp: after.random_sp,
        after_health: after.health,
        after_max_health: after.max_health,
        after_current_sp: after.current_sp,
        after_max_sp: after.max_sp,
        applied_experience: applied,
        level_rolls: rolls,
        small_potions: items.small_potions,
        medium_potions: items.medium_potions,
        stacked_items: items.stacked,
        inserted_items: items.inserted,
        dropped_items: items.dropped,
    })
}

fn insert_receipt_and_feedback(
    ctx: &ReducerContext,
    actor: Identity,
    audit: &AdminAudit,
    message: &str,
    severity: &str,
    applied_experience: u64,
) {
    ctx.db.admin_request_receipt().insert(AdminRequestReceipt {
        request_id: audit.request_id.clone(),
        actor_account: actor,
        action: audit.action.clone(),
        canonical_argument: audit.canonical_argument.clone(),
        target_account: audit.target_account,
        target_character: audit.target_character,
        outcome: audit.outcome.clone(),
        reason_code: audit.reason_code.clone(),
        severity: severity.into(),
        message: message.into(),
        created_at: audit.created_at,
        audit_id: audit.id,
        applied_experience,
    });
    upsert_feedback(ctx, actor, &audit.request_id, severity, message);
}

fn upsert_feedback(
    ctx: &ReducerContext,
    account: Identity,
    request_id: &str,
    severity: &str,
    message: &str,
) {
    let existing = ctx
        .db
        .command_feedback()
        .account()
        .filter(account)
        .find(|row| row.request_id == request_id);
    if let Some(mut row) = existing {
        row.severity = severity.into();
        row.message = message.into();
        row.created_at = ctx.timestamp;
        ctx.db.command_feedback().id().update(row);
    } else {
        ctx.db.command_feedback().insert(CommandFeedback {
            id: 0,
            account,
            request_id: request_id.into(),
            severity: severity.into(),
            message: message.into(),
            created_at: ctx.timestamp,
        });
    }
    let mut rows: Vec<_> = ctx
        .db
        .command_feedback()
        .account()
        .filter(account)
        .collect();
    rows.sort_by_key(|row| row.id);
    while rows.len() > FEEDBACK_LIMIT {
        let index = rows
            .iter()
            .position(|row| !row.request_id.is_empty())
            .unwrap_or(0);
        let row = rows.remove(index);
        ctx.db.command_feedback().id().delete(row.id);
    }
}

fn has_progression_capability(ctx: &ReducerContext, account: Identity) -> bool {
    is_bootstrap_identity(account)
        || ctx
            .db
            .progression_operator()
            .account()
            .find(account)
            .is_some_and(|row| row.enabled)
}

fn is_bootstrap_identity(identity: Identity) -> bool {
    crate::definitions::PROGRESSION_BOOTSTRAP_IDENTITIES
        .iter()
        .any(|value| canonical_identity(value) == Some(identity))
}

fn canonical_identity(value: &str) -> Option<Identity> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return None;
    }
    Identity::from_hex(value).ok()
}

fn valid_request_id(value: &str) -> bool {
    value.len() == REQUEST_ID_LEN
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn parse_positive_u32(value: &str) -> Result<u32, ()> {
    if value.is_empty() || value.len() > 10 || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(());
    }
    let mut result = 0_u32;
    for byte in value.bytes() {
        result = result.checked_mul(10).ok_or(())?;
        result = result.checked_add(u32::from(byte - b'0')).ok_or(())?;
    }
    if result == 0 {
        return Err(());
    }
    Ok(result)
}

fn canonical_numeric_intent(value: &str) -> String {
    match parse_positive_u32(value) {
        Ok(number) => number.to_string(),
        Err(()) if value.len() <= MAX_NUMERIC_INPUT_BYTES => {
            format!("invalid:{:016x}", stable_bounded_hash(value.as_bytes()))
        }
        Err(()) => format!(
            "invalid_oversize:{}:{:016x}",
            value.len(),
            stable_bounded_hash(&value.as_bytes()[..MAX_NUMERIC_INPUT_BYTES])
        ),
    }
}

fn canonical_provision_intent(
    target: Identity,
    enabled: bool,
    raw_reason: &str,
    reason: Option<&str>,
) -> String {
    match reason {
        Some(value) => format!("{}:{}:{value}", target, u8::from(enabled)),
        None => {
            let prefix = &raw_reason.as_bytes()[..raw_reason.len().min(MAX_REASON_CHARS * 4)];
            format!(
                "{}:{}:invalid_reason:{}:{:016x}",
                target,
                u8::from(enabled),
                raw_reason.len(),
                stable_bounded_hash(prefix)
            )
        }
    }
}

fn normalize_reason(value: &str) -> Option<String> {
    if value.len() > MAX_REASON_CHARS * 4 {
        return None;
    }
    let normalized = value.trim();
    let length = normalized.chars().count();
    if !(3..=MAX_REASON_CHARS).contains(&length) || normalized.chars().any(char::is_control) {
        return None;
    }
    Some(normalized.into())
}

fn stable_bounded_hash(value: &[u8]) -> u64 {
    value.iter().fold(0xcbf2_9ce4_8422_2325, |hash, byte| {
        (hash ^ u64::from(*byte)).wrapping_mul(0x0000_0100_0000_01b3)
    })
}

fn copy_roll(value: &LevelRoll) -> AdminLevelRoll {
    AdminLevelRoll {
        resulting_level: value.resulting_level,
        hp: value.hp,
        sp: value.sp,
    }
}

fn empty_snapshot() -> ProgressionSnapshot {
    ProgressionSnapshot {
        level: 0,
        experience: 0,
        level_step: 0,
        unspent_stat_points: 0,
        strength: 0,
        vitality: 0,
        dexterity: 0,
        intelligence: 0,
        random_hp: 0,
        random_sp: 0,
        health: 0,
        max_health: 0,
        current_sp: 0,
        max_sp: 0,
    }
}

fn empty_items() -> AutomaticItemSummary {
    AutomaticItemSummary {
        small_potions: 0,
        medium_potions: 0,
        stacked: 0,
        inserted: 0,
        dropped: 0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn request_ids_are_exact_lowercase_hex() {
        assert!(valid_request_id("0123456789abcdef0123456789abcdef"));
        assert!(!valid_request_id("0123456789ABCDEF0123456789ABCDEF"));
        assert!(!valid_request_id("0123456789abcdef"));
        assert!(!valid_request_id("g123456789abcdef0123456789abcdef"));
    }

    #[test]
    fn numeric_parser_is_ascii_decimal_checked_and_positive() {
        assert_eq!(parse_positive_u32("1"), Ok(1));
        assert_eq!(parse_positive_u32("0001"), Ok(1));
        assert_eq!(parse_positive_u32("4294967295"), Ok(u32::MAX));
        for invalid in [
            "",
            "0",
            "-1",
            "+1",
            "1.0",
            "1e3",
            "NaN",
            "inf",
            "１２",
            " 1",
            "1 ",
            "1 2",
            "4294967296",
        ] {
            assert_eq!(parse_positive_u32(invalid), Err(()), "accepted {invalid:?}");
        }
    }

    #[test]
    fn invalid_numeric_intents_are_bounded() {
        let normal = canonical_numeric_intent("bad value");
        let huge = canonical_numeric_intent(&"x".repeat(20_000));
        assert!(normal.starts_with("invalid:"));
        assert!(normal.len() <= 32);
        assert!(huge.starts_with("invalid_oversize:"));
        assert!(huge.len() <= 64);
    }

    #[test]
    fn bootstrap_identity_parser_rejects_noncanonical_values() {
        let identity = Identity::from_claims("test", "operator");
        let text = identity.to_string();
        assert_eq!(canonical_identity(&text), Some(identity));
        assert_eq!(canonical_identity(&text.to_uppercase()), None);
        assert_eq!(canonical_identity(&format!(" {text}")), None);
        assert_eq!(canonical_identity(&format!("{text},")), None);
    }

    #[test]
    fn provisioning_reasons_are_trimmed_printable_and_bounded() {
        assert_eq!(
            normalize_reason("  local QA operator  ").as_deref(),
            Some("local QA operator")
        );
        assert!(normalize_reason("no").is_none());
        assert!(normalize_reason("line\nbreak").is_none());
        assert!(normalize_reason(&"x".repeat(161)).is_none());
    }
}
