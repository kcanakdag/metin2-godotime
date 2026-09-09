//! Persisted charge ownership and the minimal public presentation projection.
use crate::charge_lifecycle::{Activation, Charge, Owner, State};
use crate::skills::{CharacterSkill, character_skill};
use crate::{Controller, Player, accounts, controller, definitions, player};
use spacetimedb::{ConnectionId, Identity, ReducerContext, Table};

#[spacetimedb::table(accessor = active_charge)]
pub struct ActiveCharge {
    #[primary_key]
    pub character_id: Identity,
    pub connection_id: ConnectionId,
    pub source_life: u32,
    pub skill_vnum: u16,
    pub rank: u8,
    pub starts_at_us: i64,
    pub expires_at_us: i64,
    pub speed_bonus: i32,
}

#[spacetimedb::table(accessor = charge_status, public)]
pub struct ChargeStatus {
    #[primary_key]
    pub character_id: Identity,
    pub skill_vnum: u16,
    pub starts_at_us: i64,
    pub expires_at_us: i64,
    pub speed_bonus: i32,
}

fn owner(control: &Controller, player: &Player) -> Owner {
    Owner {
        character: player.identity,
        connection: control.connection_id,
        life: player.life_sequence,
    }
}

impl ActiveCharge {
    fn charge(&self) -> Charge {
        Charge {
            owner: Owner {
                character: self.character_id,
                connection: self.connection_id,
                life: self.source_life,
            },
            rank: self.rank,
            starts_at_us: self.starts_at_us,
            expires_at_us: self.expires_at_us,
            speed_bonus: self.speed_bonus,
        }
    }
}

/// Inputs are selected, validated server rows, never reducer arguments.
pub(crate) fn activate(
    ctx: &ReducerContext,
    control: &Controller,
    player: &Player,
    skill: &CharacterSkill,
    definition: &definitions::SkillDefinition,
    current_sp: u32,
    now: i64,
) -> Result<Activation, String> {
    if control.identity != player.identity
        || skill.character_id != player.identity
        || skill.skill_vnum != definition.vnum
        || !player.online
        || player.health == 0
        || !accounts::controller_has_active_lease(ctx, control)
    {
        return Err("Charge requires the selected living controller life".into());
    }
    let definition_policy = definition.charge.ok_or("Skill has no charge policy")?;
    let captured = ctx.db.active_charge().character_id().find(player.identity);
    let state = State {
        skill_vnum: skill.skill_vnum,
        revision: skill.revision,
        ready_at_us: skill.ready_at_us,
        charge: captured.as_ref().map(ActiveCharge::charge),
    };
    let activation = state.begin(
        owner(control, player),
        skill.rank,
        definition_policy.activation_policy(
            definition.cooldown_us,
            crate::skills::sp_cost(definition, skill.rank)?,
        ),
        current_sp,
        skill.revision,
        now,
    )?;
    let charge = activation
        .state
        .charge
        .ok_or("Charge activation omitted state")?;
    ctx.db.active_charge().insert(ActiveCharge {
        character_id: player.identity,
        connection_id: control.connection_id,
        source_life: player.life_sequence,
        skill_vnum: skill.skill_vnum,
        rank: charge.rank,
        starts_at_us: charge.starts_at_us,
        expires_at_us: charge.expires_at_us,
        speed_bonus: charge.speed_bonus,
    });
    ctx.db.charge_status().insert(ChargeStatus {
        character_id: player.identity,
        skill_vnum: skill.skill_vnum,
        starts_at_us: charge.starts_at_us,
        expires_at_us: charge.expires_at_us,
        speed_bonus: charge.speed_bonus,
    });
    Ok(activation)
}

/// Include the elapsed part of an expired effect until movement is accounted for.
/// Validating ownership is separate from testing whether the effect is active now.
pub(crate) fn movement_effect(
    ctx: &ReducerContext,
    control: &Controller,
    player: &Player,
) -> Option<crate::movement::SpeedEffect> {
    if control.identity != player.identity
        || !player.online
        || player.health == 0
        || !accounts::controller_has_active_lease(ctx, control)
    {
        return None;
    }
    let row = ctx
        .db
        .active_charge()
        .character_id()
        .find(player.identity)?;
    (row.charge().owner == owner(control, player)).then_some(crate::movement::SpeedEffect {
        starts_at_us: row.starts_at_us,
        expires_at_us: row.expires_at_us,
        bonus_points: row.speed_bonus,
    })
}

/// Run after movement so expiry cannot discard earned travel inside this tick.
pub(crate) fn maintain(ctx: &ReducerContext, now: i64) {
    for row in ctx.db.active_charge().iter() {
        let current = ctx
            .db
            .controller()
            .identity()
            .find(row.character_id)
            .zip(ctx.db.player().identity().find(row.character_id))
            .filter(|(c, p)| {
                p.online && p.health > 0 && accounts::controller_has_active_lease(ctx, c)
            })
            .map(|(c, p)| owner(&c, &p));
        if row.charge().active(current, now) {
            continue;
        }
        ctx.db
            .active_charge()
            .character_id()
            .delete(row.character_id);
        ctx.db
            .charge_status()
            .character_id()
            .delete(row.character_id);
        if let Some(mut skill) = ctx
            .db
            .character_skill()
            .id()
            .find(format!("{}:{}", row.character_id, row.skill_vnum))
        {
            // An exhausted revision prevents future casts, but must not stall the
            // whole world's cleanup or retain a dead/disconnected affect forever.
            skill.revision = skill.revision.saturating_add(1);
            ctx.db.character_skill().id().update(skill);
        }
    }
}
