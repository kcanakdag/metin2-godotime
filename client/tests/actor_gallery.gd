extends Node3D
## Offline review scene for the generated Warrior, starter sword, and Wild Dog.

const ActorCatalogScript := preload("res://scripts/content/actor_catalog.gd")

var _catalog := ActorCatalogScript.new()
var _player: PlayerActor
var _dog: PveActor
var _player_row: Dictionary
var _dog_row: Dictionary
var _appearance: Dictionary
var _clock_us := 10_000_000

@onready var _status: Label = $HUD/Margin/Column/Status


func _ready() -> void:
	$Camera3D.look_at(Vector3(0.0, 0.75, 0.0))
	if not _catalog.load_required():
		_status.text = _catalog.error_message
		return
	_player = PlayerActor.new()
	_player.name = "SubscribedWarrior"
	_player.configure(_catalog)
	add_child(_player)
	_dog = PveActor.new()
	_dog.name = "SubscribedWildDog"
	_dog.configure(_catalog)
	add_child(_dog)
	_player_row = _base_player_row()
	_dog_row = _base_dog_row()
	_appearance = _base_appearance()
	show_wait()


func show_wait() -> void:
	_player_row.activity = 0
	_player_row.action_started_at_us = 0
	_player_row.action_ends_at_us = 0
	_dog_row.activity = 0
	_dog_row.action_started_at_us = 0
	_dog_row.action_ends_at_us = 0
	_apply("Equipped wait · server heading 0 faces -Z")


func show_swing() -> void:
	var motion := _catalog.motion(
		ActorCatalogScript.WARRIOR_ID, "", "actor.player.warrior-male.onehand.combo_1"
	)
	_clock_us += 2_000_000
	_player_row.activity = 2
	_player_row.attack_sequence = int(_player_row.attack_sequence) + 1
	_player_row.attack_action_id = str(motion.action_id)
	_player_row.action_started_at_us = _clock_us - int(motion.duration_us) / 2
	_player_row.action_ends_at_us = _player_row.action_started_at_us + int(motion.duration_us)
	_dog_row.activity = 0
	_apply("Sword+0 attack · source clip midpoint")


func show_warrior_death() -> void:
	var motion := _catalog.motion(ActorCatalogScript.WARRIOR_ID, "onehand", "", "death")
	_clock_us += 2_000_000
	_player_row.activity = 3
	_player_row.life_sequence = int(_player_row.life_sequence) + 1
	_player_row.action_started_at_us = _clock_us - int(motion.duration_us) - 1
	_player_row.action_ends_at_us = _clock_us + 5_000_000
	_dog_row.activity = 0
	_apply("Warrior death · held at final source pose")


func show_dog_attack() -> void:
	var motion := _catalog.motion(
		ActorCatalogScript.WILD_DOG_ID, "", "actor.mob.wild-dog-101.general.normal_attack.v1"
	)
	_clock_us += 2_000_000
	_player_row.activity = 0
	_dog_row.activity = 2
	_dog_row.attack_sequence = int(_dog_row.attack_sequence) + 1
	_dog_row.attack_action_id = str(motion.action_id)
	_dog_row.action_started_at_us = _clock_us - int(motion.duration_us) / 2
	_dog_row.action_ends_at_us = _dog_row.action_started_at_us + int(motion.duration_us)
	_apply("Original Wild Dog 101 attack · source clip midpoint")


func show_dog_death() -> void:
	var motion := _catalog.motion(ActorCatalogScript.WILD_DOG_ID, "general", "", "front_death")
	_clock_us += 2_000_000
	_player_row.activity = 0
	_dog_row.activity = 3
	_dog_row.life_sequence = int(_dog_row.life_sequence) + 1
	_dog_row.action_started_at_us = _clock_us - int(motion.duration_us) - 1
	_dog_row.action_ends_at_us = _clock_us + 5_000_000
	_apply("Wild Dog 101 death · held at final source pose")


func _apply(label: String) -> void:
	_player.apply_state(_player_row, true, _appearance, _clock_us)
	_dog.apply_state(_dog_row, _clock_us)
	_status.text = label


func _unhandled_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo:
		return
	match event.keycode:
		KEY_1:
			show_wait()
		KEY_2:
			show_swing()
		KEY_3:
			show_warrior_death()
		KEY_4:
			show_dog_attack()
		KEY_5:
			show_dog_death()


func _base_player_row() -> Dictionary:
	return {
		"identity": "01".repeat(32),
		"name": "Equipped Warrior",
		"x": -0.85,
		"y": 0.0,
		"z": 0.0,
		"heading": 0.0,
		"activity": 0,
		"attack_sequence": 0,
		"life_sequence": 0,
		"attack_action_id": "",
		"action_started_at_us": 0,
		"action_ends_at_us": 0,
		"health": 100,
		"max_health": 100,
	}


func _base_appearance() -> Dictionary:
	return {
		"character_id": "01".repeat(32),
		"empire": 1,
		"character_class": 0,
		"sex": 0,
		"weapon_vnum": 10,
	}


func _base_dog_row() -> Dictionary:
	return {
		"id": 101,
		"x": 1.05,
		"y": 0.0,
		"z": 0.0,
		"heading": 0.0,
		"health": 100,
		"max_health": 100,
		"activity": 0,
		"attack_sequence": 0,
		"life_sequence": 0,
		"action_started_at_us": 0,
		"action_ends_at_us": 0,
		"definition_vnum": 101,
		"actor_id": ActorCatalogScript.WILD_DOG_ID,
		"name": "Wild Dog",
		"model_key": "stray_dog",
		"motion_set": "actor.mob.wild-dog-101.general",
		"attack_action_id": "actor.mob.wild-dog-101.general.normal_attack.v1",
	}
