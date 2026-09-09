//! Persisted charge ownership and the minimal public presentation projection.
use crate::charge_lifecycle::{Activation, Charge, Owner, State};
use crate::combat::monster;
use crate::progression::character_progression;
use crate::skills::{CharacterSkill, character_skill};
use crate::{Controller, Player, accounts, controller, definitions, player};
use spacetimedb::rand::Rng;
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

pub(crate) fn is_active(
    ctx: &ReducerContext,
    control: &Controller,
    player: &Player,
    skill_vnum: u16,
    now: i64,
) -> bool {
    control.identity == player.identity
        && player.online
        && player.health > 0
        && accounts::controller_has_active_lease(ctx, control)
        && ctx
            .db
            .active_charge()
            .character_id()
            .find(player.identity)
            .is_some_and(|row| {
                row.skill_vnum == skill_vnum
                    && row.charge().active(Some(owner(control, player)), now)
            })
}

/// A target strike is immediate and consumes charge in the damage transaction.
pub(crate) fn strike(
    ctx: &ReducerContext,
    control: &mut Controller,
    mut progression: crate::progression::CharacterProgression,
    mut skill: CharacterSkill,
    definition: &definitions::SkillDefinition,
    now: i64,
) -> Result<(), String> {
    crate::root_motion::advance_for_replacement(ctx, control, now)?;
    let caster = ctx
        .db
        .player()
        .identity()
        .find(control.identity)
        .ok_or("Charge owner disappeared")?;
    let target = crate::targeting::valid_target(
        ctx,
        control.combat_target_id,
        control.combat_target_life_sequence,
    )?;
    let heading = crate::skill_target::heading(
        [caster.x, caster.z],
        [target.x, target.z],
        definition.target_range_m,
        caster.heading,
    )?;
    let bounds = crate::collision_bounds(ctx);
    if !crate::content::clear_path(caster.x, caster.z, target.x, target.z, &bounds) {
        return Err("Charge target is blocked".into());
    }
    let mut victims = Vec::new();
    for victim in ctx.db.monster().iter() {
        if victim.health > 0
            && crate::charge_geometry::contains(
                [target.x, target.z],
                [victim.x, victim.z],
                definition.radius_m,
            )?
            && crate::content::clear_path(target.x, target.z, victim.x, victim.z, &bounds)
        {
            victims.push(victim);
        }
    }
    // Keep the selected exact life first; use stable instance order for the rest.
    victims.sort_by_key(|victim| (victim.id != target.id, victim.id));
    if victims
        .first()
        .is_none_or(|victim| victim.id != target.id || victim.life_sequence != target.life_sequence)
    {
        return Err("Charge target is no longer eligible".into());
    }
    if !is_active(ctx, control, &caster, skill.skill_vnum, now) {
        let activation = activate(
            ctx,
            control,
            &caster,
            &skill,
            definition,
            progression.current_sp,
            now,
        )?;
        progression.current_sp = activation.remaining_sp;
        skill.revision = activation.state.revision;
        skill.ready_at_us = activation.state.ready_at_us;
        // Persist payment before damage: a kill can independently grant XP/levels
        // and refill SP. Never overwrite that result with a pre-hit progression row.
        ctx.db
            .character_progression()
            .character_id()
            .update(progression.clone());
    }
    let charge = ctx
        .db
        .active_charge()
        .character_id()
        .find(caster.identity)
        .ok_or("Charge disappeared")?;
    let consumed = State {
        skill_vnum: skill.skill_vnum,
        revision: skill.revision,
        ready_at_us: skill.ready_at_us,
        charge: Some(charge.charge()),
    }
    .consume(Some(owner(control, &caster)), skill.revision, now)?;
    let appearance = crate::characters::owned_appearance(ctx, caster.identity)?;
    let action = &definitions::SKILL_ACTIONS
        .iter()
        .find(|(id, actor, _)| *id == skill.skill_vnum && *actor == appearance.actor_id)
        .ok_or("Charge animation is unavailable")?
        .2;
    let attacker = crate::physical_damage::capture_player(ctx, caster.identity, true)?;
    crate::combo::clear_chain(control);
    crate::combat::cancel_player_attack(control);
    crate::npcs::clear(ctx, caster.identity);
    crate::combat::start_player_action(
        ctx,
        control,
        crate::combat::PlayerAttackPlan {
            definition: action,
            target_id: 0,
            target_generation: 0,
            heading: Some(heading),
            can_select_target: false,
        },
        now,
    )?;
    crate::skills::clear(ctx, caster.identity);
    for mut victim in victims
        .into_iter()
        .take(usize::from(definition.max_targets))
    {
        let amount = crate::physical_damage::roll_skill_hit(
            ctx,
            caster.identity,
            definition,
            consumed.captured_rank,
            attacker,
            progression.vitality,
            &victim,
        )?;
        crate::combat::record_damage(
            ctx,
            victim.id,
            victim.life_sequence,
            caster.identity,
            control.connection_id,
            u32::from(amount),
            crate::mob_threat::DamageKind::MeleeSkill,
        )?;
        if crate::combat::apply_damage(&mut victim.health, amount) {
            crate::combat::kill_monster(ctx, &mut victim, caster.identity);
        } else if crate::training_targets::validate(&victim)?.is_none() {
            let species = crate::combat::ordinary_definition(ctx, &victim)?;
            let outcome = crate::crush::resolve(
                true,
                false,
                crate::crush::Victim {
                    // Selected ordinary registries still reject NOMOVE at compile time.
                    no_move: false,
                    main_target: victim.id == target.id,
                    already_stunned: crate::mob_affects::stunned(ctx, &victim, now),
                    stun_immune: species.immunity_flags & 1 != 0,
                },
                ctx.rng().gen_range(1..=100),
            )?;
            let position = crate::crush::displace(
                [caster.x, caster.z],
                [victim.x, victim.z],
                outcome.push_distance_m,
                &bounds,
            )?;
            victim.x = position[0];
            victim.z = position[1];
            victim.y = crate::content::height(victim.x, victim.z);
            if outcome.stun_duration_us > 0 {
                crate::mob_affects::stun(ctx, &mut victim, now, outcome.stun_duration_us)?;
            }
        }
        ctx.db.monster().id().update(victim);
    }
    ctx.db
        .active_charge()
        .character_id()
        .delete(caster.identity);
    ctx.db
        .charge_status()
        .character_id()
        .delete(caster.identity);
    skill.revision = consumed.state.revision;
    crate::skills::store(ctx, skill);
    ctx.db.controller().identity().update(control.clone());
    Ok(())
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
