//! Account authentication, stable character ownership and connection leases.
use crate::{
    Controller, Session, active_session, controller, inventory, now_us, player, progression,
    session, valid_name,
};
use spacetimedb::{AuthCtx, ConnectionId, Filter, Identity, ReducerContext, Table};

const AUTH_ISSUER: &str = match option_env!("MT2_AUTH_ISSUER") {
    Some(value) => value,
    None => "https://kcanakdag.com:8443/auth",
};
const AUTH_AUDIENCE: &str = "mt2-game";
const ALLOW_GUESTS: Option<&str> = option_env!("MT2_ALLOW_GUESTS");

#[spacetimedb::table(accessor = account_character, public)]
pub struct AccountCharacter {
    #[primary_key]
    pub character_id: Identity,
    #[index(btree)]
    pub account: Identity,
    pub slot: u8,
    pub name: String,
    pub empire: u8,
    pub character_class: u8,
    pub sex: u8,
}

#[spacetimedb::table(accessor = account_state, public)]
pub struct AccountState {
    #[primary_key]
    pub account: Identity,
    pub selected_character: Identity,
    pub in_world: bool,
}

#[spacetimedb::table(accessor = account_control)]
pub struct AccountControl {
    #[primary_key]
    pub account: Identity,
    pub connection_id: ConnectionId,
    pub expires_at_us: i64,
}

// Separate access records support account ownership and explicitly enabled
// guest-only disposable smoke tests without changing item row layouts.
#[spacetimedb::table(accessor = inventory_access, public)]
pub struct InventoryAccess {
    #[primary_key]
    pub character_id: Identity,
    #[index(btree)]
    pub account: Identity,
}

#[spacetimedb::client_visibility_filter]
const OWN_ROSTER: Filter =
    Filter::Sql("SELECT * FROM account_character WHERE account_character.account = :sender");
#[spacetimedb::client_visibility_filter]
const OWN_ACCOUNT_STATE: Filter =
    Filter::Sql("SELECT * FROM account_state WHERE account_state.account = :sender");
#[spacetimedb::client_visibility_filter]
const OWN_INVENTORY_ACCESS: Filter =
    Filter::Sql("SELECT * FROM inventory_access WHERE inventory_access.account = :sender");
#[spacetimedb::client_visibility_filter]
const OWN_INVENTORY: Filter =
    Filter::Sql("SELECT * FROM inventory_item WHERE inventory_item.account = :sender");
#[spacetimedb::client_visibility_filter]
const OWN_PROGRESSION: Filter = Filter::Sql(
    "SELECT * FROM character_progression WHERE character_progression.account = :sender",
);

fn validate_account_auth(auth: &AuthCtx, sender: Identity, now: i64) -> Result<i64, String> {
    let jwt = auth.jwt().ok_or("Sign in to an account first.")?;
    let claims: serde_json::Value =
        serde_json::from_str(jwt.raw_payload()).map_err(|_| "Invalid account credential.")?;
    let issuer = claims["iss"]
        .as_str()
        .ok_or("Account credential requires an issuer.")?;
    let subject = claims["sub"]
        .as_str()
        .filter(|sub| !sub.is_empty())
        .ok_or("Account credential requires a subject.")?;
    let audience = &claims["aud"];
    let valid_audience = audience.as_str() == Some(AUTH_AUDIENCE)
        || audience.as_array().is_some_and(|values| {
            values
                .iter()
                .any(|value| value.as_str() == Some(AUTH_AUDIENCE))
        });
    if issuer != AUTH_ISSUER || !valid_audience || Identity::from_claims(issuer, subject) != sender
    {
        return Err("This account credential has an untrusted issuer or audience.".into());
    }
    let expires = claims["exp"]
        .as_i64()
        .and_then(|seconds| seconds.checked_mul(1_000_000))
        .ok_or("Account credential requires an expiry.")?;
    if expires <= now {
        return Err("Account credential expired. Sign in again.".into());
    }
    Ok(expires)
}

fn authenticated_account(ctx: &ReducerContext) -> Result<i64, String> {
    active_session(ctx)?;
    validate_account_auth(ctx.sender_auth(), ctx.sender(), now_us(ctx))
}

pub fn authorize_connection(ctx: &ReducerContext) -> Result<(), String> {
    if ctx
        .sender_auth()
        .jwt()
        .is_some_and(|jwt| jwt.issuer() == AUTH_ISSUER)
    {
        validate_account_auth(ctx.sender_auth(), ctx.sender(), now_us(ctx))?;
        return Ok(());
    }
    if ALLOW_GUESTS != Some("1") {
        return Err("Sign in to an account first.".into());
    }
    if let Some(jwt) = ctx.sender_auth().jwt()
        && (jwt.issuer() != "localhost" || !jwt.audience().iter().any(|aud| aud == "spacetimedb"))
    {
        return Err("This credential has an untrusted issuer or audience.".into());
    }
    Ok(())
}

pub fn require_guest(ctx: &ReducerContext) -> Result<(), String> {
    active_session(ctx)?;
    if ALLOW_GUESTS != Some("1") {
        return Err("Sign in to an account first.".into());
    }
    if let Some(jwt) = ctx.sender_auth().jwt()
        && (jwt.issuer() != "localhost" || !jwt.audience().iter().any(|aud| aud == "spacetimedb"))
    {
        return Err("Use account character selection for this credential.".into());
    }
    if ctx
        .db
        .account_character()
        .character_id()
        .find(ctx.sender())
        .is_some()
    {
        return Err("This guest character belongs to an account. Sign in to that account.".into());
    }
    Ok(())
}

pub fn authenticated_controlled_account(
    ctx: &ReducerContext,
) -> Result<(AccountState, ConnectionId), String> {
    authenticated_account(ctx)?;
    let connection_id = active_session(ctx)?;
    let control = ctx
        .db
        .account_control()
        .account()
        .find(ctx.sender())
        .ok_or("Open your account first.")?;
    if control.connection_id != connection_id || control.expires_at_us <= now_us(ctx) {
        return Err("This account is controlled by another connection or has expired.".into());
    }
    let state = ctx
        .db
        .account_state()
        .account()
        .find(ctx.sender())
        .ok_or("Open your account first.")?;
    Ok((state, connection_id))
}

fn controlled_account(ctx: &ReducerContext) -> Result<AccountState, String> {
    authenticated_controlled_account(ctx).map(|(state, _)| state)
}

pub fn selected_character(ctx: &ReducerContext) -> Result<Identity, String> {
    if ctx
        .sender_auth()
        .jwt()
        .is_some_and(|jwt| jwt.issuer() == AUTH_ISSUER)
    {
        let state = controlled_account(ctx)?;
        if !state.in_world {
            return Err("Enter the selected character first.".into());
        }
        own_character(ctx, state.selected_character)?;
        Ok(state.selected_character)
    } else {
        require_guest(ctx)?;
        Ok(ctx.sender())
    }
}

fn own_character(ctx: &ReducerContext, character: Identity) -> Result<AccountCharacter, String> {
    let row = ctx
        .db
        .account_character()
        .character_id()
        .find(character)
        .ok_or("That character does not belong to your account.")?;
    if row.account != ctx.sender() {
        return Err("That character does not belong to your account.".into());
    }
    Ok(row)
}

fn character_id(account: Identity, slot: u8) -> Identity {
    Identity::from_claims(
        "urn:metin2-godotime:character:v1",
        &format!("{account}:{slot}"),
    )
}

pub fn ensure_guest_access(ctx: &ReducerContext, character: Identity) {
    if ctx
        .db
        .inventory_access()
        .character_id()
        .find(character)
        .is_none()
    {
        ctx.db.inventory_access().insert(InventoryAccess {
            character_id: character,
            account: character,
        });
    }
}

pub fn owner_account(ctx: &ReducerContext, character: Identity) -> Option<Identity> {
    ctx.db
        .inventory_access()
        .character_id()
        .find(character)
        .map(|row| row.account)
}

fn account_lease_matches(
    now: i64,
    character: Identity,
    controller_connection: ConnectionId,
    live_session: &Session,
    ownership: &AccountCharacter,
    lease: &AccountControl,
    state: &AccountState,
) -> bool {
    ownership.character_id == character
        && live_session.connection_id == controller_connection
        && live_session.identity == ownership.account
        && lease.account == ownership.account
        && lease.connection_id == controller_connection
        && lease.expires_at_us > now
        && state.account == ownership.account
        && state.in_world
        && state.selected_character == character
}

/// Revalidate the persisted controller against the current server-owned
/// connection/account lease. Scheduled combo transitions cannot rely on a
/// reducer sender and therefore use this exact persisted relationship.
pub fn controller_has_active_lease(ctx: &ReducerContext, control: &Controller) -> bool {
    let Some(live_session) = ctx.db.session().connection_id().find(control.connection_id) else {
        return false;
    };
    if let Some(ownership) = ctx
        .db
        .account_character()
        .character_id()
        .find(control.identity)
    {
        let Some(lease) = ctx.db.account_control().account().find(ownership.account) else {
            return false;
        };
        let Some(state) = ctx.db.account_state().account().find(ownership.account) else {
            return false;
        };
        return account_lease_matches(
            now_us(ctx),
            control.identity,
            control.connection_id,
            &live_session,
            &ownership,
            &lease,
            &state,
        );
    }
    ALLOW_GUESTS == Some("1")
        && live_session.identity == control.identity
        && owner_account(ctx, control.identity) == Some(control.identity)
}

pub fn unique_name(ctx: &ReducerContext, name: &str) -> Result<(), String> {
    let folded = name.to_lowercase();
    // Scanning existing names reserves legacy duplicates without rewriting them.
    if ctx
        .db
        .player()
        .iter()
        .any(|row| row.name.to_lowercase() == folded)
    {
        return Err("That character name is already taken.".into());
    }
    Ok(())
}

#[spacetimedb::reducer]
pub fn open_account(ctx: &ReducerContext) -> Result<(), String> {
    let expires_at_us = authenticated_account(ctx)?;
    let connection_id = active_session(ctx)?;
    if let Some(previous) = ctx.db.account_control().account().find(ctx.sender()) {
        if previous.connection_id != connection_id
            && previous.expires_at_us > now_us(ctx)
            && ctx
                .db
                .session()
                .connection_id()
                .find(previous.connection_id)
                .is_some()
        {
            return Err("This account is already open in another connection.".into());
        }
        if previous.connection_id != connection_id {
            stop_account(ctx, ctx.sender());
        }
        ctx.db.account_control().account().update(AccountControl {
            account: ctx.sender(),
            connection_id,
            expires_at_us,
        });
    } else {
        ctx.db.account_control().insert(AccountControl {
            account: ctx.sender(),
            connection_id,
            expires_at_us,
        });
    }
    if ctx
        .db
        .account_state()
        .account()
        .find(ctx.sender())
        .is_none()
    {
        ctx.db.account_state().insert(AccountState {
            account: ctx.sender(),
            selected_character: Identity::ZERO,
            in_world: false,
        });
    }
    Ok(())
}

#[spacetimedb::reducer]
pub fn create_character(
    ctx: &ReducerContext,
    slot: u8,
    name: String,
    character_class: u8,
    sex: u8,
) -> Result<(), String> {
    let mut state = controlled_account(ctx)?;
    crate::characters::appearance(character_class, sex)?;
    if slot >= 4 {
        return Err("Character slot must be between 0 and 3.".into());
    }
    if state.in_world {
        return Err("Leave the world before creating a character.".into());
    }
    if ctx
        .db
        .account_character()
        .account()
        .filter(ctx.sender())
        .any(|row| row.slot == slot)
    {
        return Err("That character slot is occupied.".into());
    }
    let name = valid_name(&name)?;
    unique_name(ctx, name)?;
    let character = character_id(ctx.sender(), slot);
    if ctx.db.player().identity().find(character).is_some() {
        return Err("That character identifier is already in use.".into());
    }
    crate::create_player(ctx, character, name, false);
    ctx.db.account_character().insert(AccountCharacter {
        character_id: character,
        account: ctx.sender(),
        slot,
        name: name.into(),
        empire: 1,
        character_class,
        sex,
    });
    ctx.db.inventory_access().insert(InventoryAccess {
        character_id: character,
        account: ctx.sender(),
    });
    progression::create_character(ctx, character, ctx.sender())?;
    inventory::ensure_starter(ctx, character)?;
    state.selected_character = character;
    ctx.db.account_state().account().update(state);
    Ok(())
}

#[spacetimedb::reducer]
pub fn select_character(ctx: &ReducerContext, character_id: Identity) -> Result<(), String> {
    let mut state = controlled_account(ctx)?;
    own_character(ctx, character_id)?;
    if state.in_world {
        stop_character(ctx, state.selected_character);
    }
    state.selected_character = character_id;
    state.in_world = false;
    ctx.db.account_state().account().update(state);
    Ok(())
}

#[spacetimedb::reducer]
pub fn enter_selected_character(ctx: &ReducerContext) -> Result<(), String> {
    let mut state = controlled_account(ctx)?;
    own_character(ctx, state.selected_character)?;
    crate::enter_character(ctx, state.selected_character)?;
    state.in_world = true;
    ctx.db.account_state().account().update(state);
    Ok(())
}

#[spacetimedb::reducer]
pub fn leave_world(ctx: &ReducerContext) -> Result<(), String> {
    if ctx
        .sender_auth()
        .jwt()
        .is_some_and(|jwt| jwt.issuer() == AUTH_ISSUER)
    {
        controlled_account(ctx)?;
        stop_account(ctx, ctx.sender());
    } else {
        require_guest(ctx)?;
        if let Some(control) = ctx.db.controller().identity().find(ctx.sender())
            && control.connection_id != active_session(ctx)?
        {
            return Err("This identity is controlled by another connection.".into());
        }
        stop_character(ctx, ctx.sender());
    }
    Ok(())
}

pub fn stop_character(ctx: &ReducerContext, character: Identity) {
    crate::npcs::clear(ctx, character);
    crate::item_effects::clear(ctx, character);
    crate::appearance::remove(ctx, character);
    crate::special_area::clear(ctx, character);
    if let Some(mut control) = ctx.db.controller().identity().find(character) {
        control.mode = 0;
        control.direction_x = 0.0;
        control.direction_z = 0.0;
        control.attack_until_us = 0;
        crate::combat::cancel_player_attack(&mut control);
        crate::combo::clear_chain(&mut control);
        crate::root_motion::clear(&mut control);
        crate::targeting::clear_character_target(ctx, &mut control)
            .unwrap_or_else(|error| panic!("cannot clear stopped character target: {error}"));
        ctx.db.controller().identity().update(control);
    }
    crate::combat::cancel_attacks_targeting(ctx, character);
    if let Some(mut player) = ctx.db.player().identity().find(character) {
        player.online = false;
        player.activity = if player.health == 0 { 3 } else { 0 };
        if player.health > 0 {
            player.action_started_at_us = 0;
            player.action_ends_at_us = 0;
        }
        ctx.db.player().identity().update(player);
    }
}

fn stop_account(ctx: &ReducerContext, account: Identity) {
    if let Some(mut state) = ctx.db.account_state().account().find(account) {
        if state.in_world {
            stop_character(ctx, state.selected_character);
        }
        state.in_world = false;
        ctx.db.account_state().account().update(state);
    }
}

pub fn disconnected(ctx: &ReducerContext, connection_id: ConnectionId) {
    if let Some(control) = ctx.db.account_control().account().find(ctx.sender())
        && control.connection_id == connection_id
    {
        stop_account(ctx, ctx.sender());
    }
    // Guest testing still checks the controlling connection, not only identity.
    if let Some(control) = ctx.db.controller().identity().find(ctx.sender())
        && control.connection_id == connection_id
    {
        stop_character(ctx, ctx.sender());
    }
}

pub fn maintain(ctx: &ReducerContext) {
    for control in ctx.db.account_control().iter() {
        if control.expires_at_us <= now_us(ctx)
            && ctx
                .db
                .account_state()
                .account()
                .find(control.account)
                .is_some_and(|state| state.in_world)
        {
            stop_account(ctx, control.account);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn auth(issuer: &str, audience: serde_json::Value, exp: i64) -> AuthCtx {
        AuthCtx::from_jwt_payload(
            serde_json::json!({"iss": issuer, "sub": "test-account", "aud": audience, "exp": exp})
                .to_string(),
        )
    }

    #[test]
    fn account_credentials_require_exact_issuer_audience_identity_and_expiry() {
        let sender = Identity::from_claims(AUTH_ISSUER, "test-account");
        let good = auth(AUTH_ISSUER, serde_json::json!([AUTH_AUDIENCE]), 300);
        assert_eq!(
            validate_account_auth(&good, sender, 1).unwrap(),
            300_000_000
        );
        assert!(validate_account_auth(&good, Identity::ZERO, 1).is_err());
        assert!(validate_account_auth(&good, sender, 300_000_000).is_err());
        for issuer in ["https://untrusted.example/auth", "localhost"] {
            assert!(
                validate_account_auth(
                    &auth(issuer, serde_json::json!(AUTH_AUDIENCE), 300),
                    sender,
                    1
                )
                .is_err()
            );
        }
        for audience in [
            serde_json::json!("wrong"),
            serde_json::json!([]),
            serde_json::Value::Null,
        ] {
            assert!(validate_account_auth(&auth(AUTH_ISSUER, audience, 300), sender, 1).is_err());
        }
        assert!(validate_account_auth(&AuthCtx::internal(), sender, 1).is_err());
    }

    #[test]
    fn character_ids_are_stable_and_account_slot_domain_separated() {
        let a = Identity::from_claims(AUTH_ISSUER, "a");
        let b = Identity::from_claims(AUTH_ISSUER, "b");
        let mut ids = std::collections::HashSet::new();
        for account in [a, b] {
            for slot in 0..4 {
                let id = character_id(account, slot);
                assert_eq!(id, character_id(account, slot));
                assert_ne!(id, account);
                assert_ne!(id, Identity::ZERO);
                assert!(ids.insert(id));
            }
        }
    }

    #[test]
    fn combo_lease_requires_exact_live_account_character_connection() {
        let account = Identity::from_claims(AUTH_ISSUER, "lease-account");
        let character = character_id(account, 0);
        let connection = ConnectionId::from_u128(7);
        let mut live_session = Session {
            connection_id: connection,
            identity: account,
        };
        let ownership = AccountCharacter {
            character_id: character,
            account,
            slot: 0,
            name: "LeaseCheck".into(),
            empire: 1,
            character_class: 0,
            sex: 0,
        };
        let mut lease = AccountControl {
            account,
            connection_id: connection,
            expires_at_us: 20,
        };
        let mut state = AccountState {
            account,
            selected_character: character,
            in_world: true,
        };
        assert!(account_lease_matches(
            10,
            character,
            connection,
            &live_session,
            &ownership,
            &lease,
            &state,
        ));

        live_session.identity = Identity::ZERO;
        assert!(!account_lease_matches(
            10,
            character,
            connection,
            &live_session,
            &ownership,
            &lease,
            &state,
        ));
        live_session.identity = account;
        live_session.connection_id = ConnectionId::from_u128(8);
        assert!(!account_lease_matches(
            10,
            character,
            connection,
            &live_session,
            &ownership,
            &lease,
            &state,
        ));
        live_session.connection_id = connection;
        lease.connection_id = ConnectionId::from_u128(8);
        assert!(!account_lease_matches(
            10,
            character,
            connection,
            &live_session,
            &ownership,
            &lease,
            &state,
        ));
        lease.connection_id = connection;
        lease.expires_at_us = 10;
        assert!(!account_lease_matches(
            10,
            character,
            connection,
            &live_session,
            &ownership,
            &lease,
            &state,
        ));
        lease.expires_at_us = 20;
        state.selected_character = Identity::ZERO;
        assert!(!account_lease_matches(
            10,
            character,
            connection,
            &live_session,
            &ownership,
            &lease,
            &state,
        ));
        state.selected_character = character;
        state.in_world = false;
        assert!(!account_lease_matches(
            10,
            character,
            connection,
            &live_session,
            &ownership,
            &lease,
            &state,
        ));
    }
}
