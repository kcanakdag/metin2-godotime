//! Validate the independent item registry and generate bounded runtime records.
use serde_json::{Map, Value, json};
use std::collections::BTreeSet;
use std::fmt::Write;

pub fn recovery_fixture_enabled(
    selected: &str,
    issuer: &str,
    yongan: bool,
    combat_fixture: &str,
    guests: bool,
    bootstrap: &str,
) -> Result<bool, String> {
    if selected.is_empty() {
        return Ok(false);
    }
    let port = issuer
        .strip_prefix("http://127.0.0.1:")
        .and_then(|value| value.strip_suffix("/auth"))
        .filter(|value| !value.is_empty() && value.bytes().all(|c| c.is_ascii_digit()))
        .and_then(|value| value.parse::<u16>().ok());
    if selected != "recovery"
        || !port.is_some_and(|port| port > 0)
        || yongan
        || !combat_fixture.is_empty()
        || guests
        || !bootstrap.is_empty()
    {
        return Err("recovery item fixture requires isolated training, loopback auth, no guests and no privileges".into());
    }
    Ok(true)
}

fn object<'a>(value: &'a Value, fields: &[&str]) -> Result<&'a Map<String, Value>, String> {
    let row = value.as_object().ok_or("item record must be an object")?;
    if row.len() != fields.len() || fields.iter().any(|key| !row.contains_key(*key)) {
        return Err("item record has missing or unsupported fields".into());
    }
    Ok(row)
}

fn number(value: &Value, min: u32, max: u32) -> Result<u32, String> {
    value
        .as_u64()
        .filter(|n| *n >= u64::from(min) && *n <= u64::from(max))
        .map(|n| n as u32)
        .ok_or_else(|| format!("item number must be an integer in {min}..={max}"))
}

pub fn validate_links(root: &Value) -> Result<(), String> {
    let items = root["item_catalog"]["items"]
        .as_array()
        .ok_or("missing item registry")?;
    for weapon in root["physical_damage"]["weapons"]
        .as_array()
        .ok_or("missing physical weapons")?
    {
        let item = items
            .iter()
            .find(|item| item["id"] == weapon["item_id"])
            .ok_or("physical weapon is absent from item registry")?;
        if item["vnum"] != weapon["vnum"]
            || ["class", "power_min", "power_max", "refine_attack"]
                .iter()
                .any(|key| item["weapon"][key] != weapon[key])
        {
            return Err("item registry and physical weapon definitions disagree".into());
        }
    }
    for reward in root["progression"]["reward_items"]
        .as_array()
        .ok_or("missing item rewards")?
    {
        let item = items
            .iter()
            .find(|item| item["vnum"] == reward["vnum"])
            .ok_or("reward item is absent from registry")?;
        if item["height"] != reward["size"] || item["stack_limit"] != reward["stack_limit"] {
            return Err("item reward placement or stack rules disagree with registry".into());
        }
    }
    Ok(())
}

pub fn generate(value: &Value) -> Result<String, String> {
    let root = object(value, &["schema_version", "recovery_policy", "items"])?;
    number(&root["schema_version"], 3, 3)?;
    if root["recovery_policy"]
        != json!({
            "id": "item.recovery.pool.v1", "interval_us": 1_000_000,
            "maximum_percent_per_tick": 7, "potion_bonus_percent": 0,
            "offline_policy": "discard-on-leave", "late_tick_policy": "one-step-no-catchup"
        })
    {
        return Err("unsupported item recovery policy".into());
    }
    let items = root["items"].as_array().ok_or("items must be an array")?;
    if items.is_empty() || items.len() > 65535 {
        return Err("item registry needs 1..65535 records".into());
    }
    let mut output = String::from(
        "#[derive(Clone, Copy, Debug, PartialEq, Eq)]\n\
         pub enum ItemKind {\n\
         Weapon,\n\
         Recovery { hp: u32, sp: u32 },\n\
         /// Wearable armour. The category and wear position are preserved so\n\
         /// later equipment work can use them; item bonuses are not modelled yet.\n\
         Armor { category: &'static str, position: &'static str },\n\
         /// Quest or miscellaneous item without an implemented mechanic.\n\
         Narrative,\n\
         }\n\
         #[derive(Clone, Copy, Debug)]\n\
         pub struct ItemDefinition {\n\
         pub id: &'static str, pub vnum: u32, pub name: &'static str,\n\
         pub height: u8, pub stack_limit: u16, pub minimum_level: u8,\n\
         pub attack_speed_bonus: u16, pub allowed_classes: u8, pub allowed_sexes: u8, pub kind: ItemKind,\n\
         pub weapon: Option<WeaponPhysicalDefinition> }\n\
         pub const RECOVERY_INTERVAL_US: i64 = 1_000_000;\n\
         pub const RECOVERY_PERCENT: u32 = 7;\n\
         pub const ITEM_DEFINITIONS: &[ItemDefinition] = &[\n",
    );
    let mut ids = BTreeSet::new();
    let mut previous_vnum = 0;
    for value in items {
        let row = object(
            value,
            &[
                "id",
                "revision",
                "vnum",
                "name",
                "icon",
                "height",
                "stack_limit",
                "minimum_level",
                "allowed_classes",
                "allowed_sexes",
                "attack_speed_bonus",
                "kind",
                "weapon",
                "recovery",
                "armor",
                "source",
            ],
        )?;
        let id = row["id"].as_str().ok_or("item id must be a string")?;
        if !id.starts_with("item.")
            || id.len() < 6
            || id.len() > 125
            || !id.as_bytes()[5].is_ascii_alphanumeric()
            || !id
                .bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || b"._-".contains(&c))
            || !ids.insert(id)
        {
            return Err("invalid or duplicate item id".into());
        }
        let vnum = number(&row["vnum"], 1, u32::MAX)?;
        if vnum <= previous_vnum {
            return Err("item vnums must be unique and sorted".into());
        }
        previous_vnum = vnum;
        number(&row["revision"], 1, 65535)?;
        let height = number(&row["height"], 1, 9)?;
        let stack_limit = number(&row["stack_limit"], 1, 200)?;
        let minimum_level = number(&row["minimum_level"], 0, 255)?;
        let allowed_classes = number(&row["allowed_classes"], 1, 15)?;
        let attack_speed_bonus = number(&row["attack_speed_bonus"], 0, 1000)?;
        let allowed_sexes = number(&row["allowed_sexes"], 1, 3)?;
        let name = row["name"].as_str().ok_or("item name must be text")?;
        if name.is_empty() || name.chars().count() > 80 || name.chars().any(|c| (c as u32) < 32) {
            return Err("invalid item name".into());
        }
        let icon = row["icon"]
            .as_str()
            .and_then(|s| s.strip_prefix("icon/item/"))
            .ok_or("invalid item icon")?;
        if !(5..=10).contains(&icon.len()) || !icon.bytes().all(|c| c.is_ascii_digit()) {
            return Err("invalid item icon".into());
        }
        let source = object(
            &row["source"],
            &["path", "revision", "git_sha", "sha256", "row_number"],
        )?;
        if source["path"] != "gamefiles/conf/item_proto.txt" {
            return Err("unsupported item source".into());
        }
        for (key, length) in [("revision", 40), ("git_sha", 40), ("sha256", 64)] {
            let hash = source[key].as_str().ok_or("invalid item source hash")?;
            if hash.len() != length
                || !hash
                    .bytes()
                    .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
            {
                return Err("invalid item source hash".into());
            }
        }
        number(&source["row_number"], 2, u32::MAX)?;
        let (kind, weapon) = match row["kind"].as_str() {
            Some("weapon") => {
                let w = object(
                    &row["weapon"],
                    &["class", "power_min", "power_max", "refine_attack"],
                )?;
                let class = match w["class"].as_str() {
                    Some("sword") => "Sword",
                    Some("fan") => "Fan",
                    _ => return Err("unsupported physical weapon class".into()),
                };
                if !row["recovery"].is_null() || stack_limit != 1 {
                    return Err("unsupported weapon kind or stack".into());
                }
                let low = number(&w["power_min"], 0, 65535)?;
                let high = number(&w["power_max"], 0, 65535)?;
                let refine = number(&w["refine_attack"], 0, 65535)?;
                if low > high || high + refine > 65535 {
                    return Err("invalid weapon range".into());
                }
                (
                    String::from("ItemKind::Weapon"),
                    format!(
                        "Some(WeaponPhysicalDefinition {{ item_id: {id:?}, vnum: {vnum}, class: PhysicalWeaponClass::{class}, power_min: {low}, power_max: {high}, refine_attack: {refine} }})"
                    ),
                )
            }
            Some("recovery") => {
                let effect = object(&row["recovery"], &["handler", "hp", "sp"])?;
                if effect["handler"] != "item.recovery.pool.v1" || !row["weapon"].is_null() {
                    return Err("unsupported recovery handler".into());
                }
                let hp = number(&effect["hp"], 0, 65535)?;
                let sp = number(&effect["sp"], 0, 65535)?;
                if hp + sp == 0 {
                    return Err("empty recovery effect".into());
                }
                (
                    format!("ItemKind::Recovery {{ hp: {hp}, sp: {sp} }}"),
                    String::from("None"),
                )
            }
            Some("armor") => {
                let armor = object(&row["armor"], &["category", "position"])?;
                if !row["recovery"].is_null() || !row["weapon"].is_null() {
                    return Err("unsupported armor mechanic".into());
                }
                let category = armor["category"]
                    .as_str()
                    .filter(|value| !value.is_empty() && value.len() <= 32)
                    .ok_or("armor category must be text")?;
                let position = armor["position"]
                    .as_str()
                    .filter(|value| !value.is_empty() && value.len() <= 32)
                    .ok_or("armor position must be text")?;
                (
                    format!("ItemKind::Armor {{ category: {category:?}, position: {position:?} }}"),
                    String::from("None"),
                )
            }
            Some("narrative") => {
                if !row["recovery"].is_null() || !row["weapon"].is_null() || !row["armor"].is_null()
                {
                    return Err("narrative items must not declare a mechanic".into());
                }
                (String::from("ItemKind::Narrative"), String::from("None"))
            }
            _ => return Err("unsupported item mechanic".into()),
        };
        writeln!(output, "ItemDefinition {{ id: {id:?}, vnum: {vnum}, name: {name:?}, height: {height}, stack_limit: {stack_limit}, minimum_level: {minimum_level}, allowed_classes: {allowed_classes}, allowed_sexes: {allowed_sexes}, attack_speed_bonus: {attack_speed_bonus}, kind: {kind}, weapon: {weapon} }},").unwrap();
    }
    output.push_str("] ;\n");
    Ok(output)
}
