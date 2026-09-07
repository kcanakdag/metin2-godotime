extends SceneTree
## Isolated catalog, resource, discrete-clock, and malformed-data checks.

var _checks := 0
var _failed := false
var _catalog := TargetEffectCatalog.new()


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_check(
		_catalog.load_required(),
		"installed target-effect catalog loads: %s" % _catalog.error_message
	)
	if _failed:
		_finish()
		return
	_test_catalog()
	_test_resources_and_clock()
	_test_malformed()
	_finish()


func _test_catalog() -> void:
	_check(_catalog.content_hash().length() == 64, "catalog content hash is present")
	_check(
		_catalog.resource_path("models/click_select.glb").begins_with(
			TargetEffectCatalog.RESOURCE_ROOT
		),
		"catalog resolves packaged resources only beneath its fixed root"
	)
	_check(
		_catalog.effect(TargetEffectCatalog.HOVER_ID).layers == ["click_select"],
		"hover keeps one alpha layer"
	)
	_check(
		(
			_catalog.effect(TargetEffectCatalog.TARGET_ID).layers
			== ["click_select", "click_glow_select"]
		),
		"combat target keeps simultaneous alpha and additive layers"
	)
	_check(
		_catalog.effect(TargetEffectCatalog.TARGET_ID).runtime_offset_m == [0.0, 0.0, 0.0],
		"runtime offset stays zero because source position is baked"
	)


func _test_resources_and_clock() -> void:
	var hover := TargetEffect.new()
	root.add_child(hover)
	_check(
		hover.configure(_catalog, TargetEffectCatalog.HOVER_ID),
		"hover instantiates its converted GLB and materials: %s" % hover.error_message
	)
	if hover.snapshot().layer_count != 1:
		hover.free()
		return
	hover.set_process(false)
	_check(hover.snapshot().layer_count == 1, "hover owns one model layer")
	_check(hover.snapshot().alpha_u8 == [[255, 255]], "frame zero applies both surface alphas")
	_check(
		hover.snapshot().morph_weights == [[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]],
		"frame zero uses the imported basis geometry"
	)
	_check(
		(
			hover.snapshot().mesh_bounds[0].size[0] > 1.9
			and hover.snapshot().mesh_bounds[0].size[1] < 0.07
			and hover.snapshot().mesh_bounds[0].size[2] > 1.9
		),
		"imported hover geometry is a thin horizontal two-meter ring"
	)

	hover.reset_clock()
	hover._process(0.019999)
	_check(
		hover.snapshot().frame == 0 and hover.snapshot().remaining_us == 1,
		"19,999us remains on frame zero"
	)
	hover.reset_clock()
	hover._process(0.020000)
	_check(
		hover.snapshot().frame == 0 and hover.snapshot().remaining_us == 0,
		"exact 20,000us boundary keeps the prior frame"
	)
	hover.reset_clock()
	hover._process(0.020001)
	_check(
		(
			hover.snapshot().frame == 1
			and hover.snapshot().remaining_us == 19_999
			and hover.snapshot().morph_weights[0][0] == 1.0
		),
		"20,001us advances exactly one frame"
	)
	for frame in range(2, 11):
		hover._process(0.020000)
		var weights: Array = hover.snapshot().morph_weights[0]
		var expected_weights: Array[float] = []
		for morph in 10:
			expected_weights.append(1.0 if morph == frame - 1 else 0.0)
		_check(
			weights == expected_weights,
			"source frame %d selects its actual imported STEP morph key" % frame
		)
	hover.reset_clock()
	hover._process(0.200001)
	_check(
		(
			hover.snapshot().frame == 10
			and hover.snapshot().alpha_u8 == [[0, 0]]
			and hover.snapshot().morph_weights[0][9] == 1.0
		),
		"last source frame uses quantized zero alpha"
	)
	hover._process(0.020000)
	_check(hover.snapshot().frame == 0, "the eleven-frame sequence loops to frame zero")

	hover.reset_clock()
	hover._process(1.0)
	_check(
		(
			hover.snapshot().frame == 9
			and hover.snapshot().remaining_us == -580_000
			and hover.snapshot().last_advances == 20
		),
		"one-second stall advances at most 20 and retains its negative remainder"
	)
	hover._process(0.0)
	_check(
		(
			hover.snapshot().frame == 7
			and hover.snapshot().remaining_us == -180_000
			and hover.snapshot().last_advances == 20
		),
		"a zero-delta update continues consuming retained stall remainder"
	)
	hover._process(0.0)
	_check(
		(
			hover.snapshot().frame == 5
			and hover.snapshot().remaining_us == 0
			and hover.snapshot().last_advances == 9
		),
		"retained remainder reaches the source frame and exact zero boundary"
	)

	var target := TargetEffect.new()
	root.add_child(target)
	_check(
		target.configure(_catalog, TargetEffectCatalog.TARGET_ID),
		"combat target instantiates its shared base and additive glow"
	)
	target.set_process(false)
	_check(target.snapshot().layer_count == 2, "combat target owns two simultaneous layers")
	_check(
		target.snapshot().alpha_u8 == [[255, 255], [255, 255]],
		"both combat-target layers start on synchronized frame zero"
	)
	target._process(0.100001)
	var target_weights: Array = target.snapshot().morph_weights
	_check(
		(
			target.snapshot().frame == 5
			and target_weights[0][4] == 1.0
			and target_weights[1][4] == 1.0
		),
		"base and additive target models select the same imported frame-five morph"
	)
	_check(not target.configure(_catalog, "effect.actor.unknown"), "unknown effect IDs fail closed")
	hover.free()
	target.free()


func _test_malformed() -> void:
	var source: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(TargetEffectCatalog.CATALOG_PATH)
	)
	var malformed := source.duplicate(true)
	malformed["unknown"] = true
	_check(not _load_silent(malformed), "unknown catalog fields are rejected")

	malformed = source.duplicate(true)
	malformed.playback.frame_count = 12
	_check(not _load_silent(malformed), "unexpected frame counts are rejected")

	malformed = source.duplicate(true)
	malformed.effects[0].runtime_offset_m = [0.0, 0.0]
	_check(not _load_silent(malformed), "malformed runtime vectors are rejected")
	malformed = source.duplicate(true)
	malformed.effects[0].runtime_offset_m = [1.0e-100, 0.0, 0.0]
	_check(not _load_silent(malformed), "tiny nonzero runtime offsets are rejected")

	malformed = source.duplicate(true)
	malformed.assets[0].surfaces[0].frame_alpha_u8[0] = 256
	_check(not _load_silent(malformed), "out-of-range alpha bytes are rejected")

	malformed = source.duplicate(true)
	malformed.files["models/click_select.glb"].bytes = 1.5
	_check(not _load_silent(malformed), "non-integer byte counts are rejected")

	malformed = source.duplicate(true)
	malformed.resource_root = "res://assets/source"
	_check(not _load_silent(malformed), "resource-root changes are rejected")

	malformed = source.duplicate(true)
	malformed.effects.append(malformed.effects[1].duplicate(true))
	_check(not _load_silent(malformed), "duplicate effect IDs are rejected")

	var reloaded := TargetEffectCatalog.new()
	_check(reloaded.load_document(source), "reload fixture starts from a valid catalog")
	_check(
		(
			not reloaded.load_required("user://missing-target-effect-catalog.json")
			and not reloaded.loaded
			and reloaded.asset("click_select").is_empty()
			and reloaded.effect(TargetEffectCatalog.HOVER_ID).is_empty()
		),
		"a missing reload clears previously accepted catalog state"
	)
	var invalid := FileAccess.open("user://invalid-target-effect-catalog.json", FileAccess.WRITE)
	invalid.store_string("{")
	invalid.close()
	_check(reloaded.load_document(source), "invalid-JSON reload fixture restores valid state")
	_check(
		(
			not reloaded.load_required("user://invalid-target-effect-catalog.json")
			and not reloaded.loaded
			and reloaded.effect(TargetEffectCatalog.TARGET_ID).is_empty()
		),
		"an invalid-JSON reload clears previously accepted catalog state"
	)


func _load_silent(document: Dictionary) -> bool:
	var catalog := TargetEffectCatalog.new()
	return catalog.load_document(document)


func _check(passed: bool, description: String) -> void:
	if passed:
		_checks += 1
		return
	_failed = true
	push_error("TARGET_EFFECT_SMOKE FAIL " + description)


func _finish() -> void:
	if not _failed:
		print("TARGET_EFFECT_SMOKE PASS ", _checks, " checks")
	quit(1 if _failed else 0)
