extends SceneTree
## Run by tools/generate_bindings.py in an isolated project with the pinned SDK.


func _initialize() -> void:
	var schema_path := "res://schema.json"
	var module_config := SpacetimeDBModuleConfig.new()
	module_config.name = "mt2-dev-world"
	module_config.alias = "game"
	module_config.hide_private_tables = true
	module_config.unparsed_module_schema = FileAccess.get_file_as_string(schema_path)
	if module_config.unparsed_module_schema.is_empty():
		printerr("Schema input is missing: ", schema_path)
		quit(1)
		return
	var config := SpacetimeDBPluginConfig.new()
	config.module_configs["game"] = module_config
	var codegen := SpacetimeCodegen.new("res://spacetime_bindings/schema")
	codegen._plugin_config = config
	var files := codegen.generate_bindings()
	if (
		files.is_empty()
		or not FileAccess.file_exists("res://spacetime_bindings/schema/module_game_client.gd")
	):
		printerr("Binding generation failed; verify the published server schema.")
		quit(1)
		return
	print("MT2_BINDINGS_GENERATED ", files.size())
	quit(0)
