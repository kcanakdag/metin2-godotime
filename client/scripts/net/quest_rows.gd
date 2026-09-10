class_name QuestRows
extends RefCounted
## Account-private quest snapshot: quest states, tracked letter objectives and
## the pending scripted selection. The server filters every table by account, so
## whatever arrives here already belongs to the signed-in player.

var states: Array = []
var objectives: Array = []
var selection: Dictionary = {}


func ingest(table: String, rows: Array) -> void:
	match table:
		"quest_state", "quest_objective":
			rows.sort_custom(_by_quest_index)
			if table == "quest_state":
				states = rows
			else:
				objectives = rows
		"quest_selection":
			selection = rows[0] if not rows.is_empty() else {}


func clear() -> void:
	states = []
	objectives = []
	selection = {}


func state_for(quest_id: String) -> Dictionary:
	for row: Dictionary in states:
		if str(row.get("quest_id", "")) == quest_id:
			return row
	return {}


func objective_for(quest_id: String) -> Dictionary:
	for row: Dictionary in objectives:
		if str(row.get("quest_id", "")) == quest_id:
			return row
	return {}


func _by_quest_index(a: Dictionary, b: Dictionary) -> bool:
	return int(a.get("quest_index", 0)) < int(b.get("quest_index", 0))
