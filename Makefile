GODOT ?= godot
BLENDER ?= blender
SPACETIME ?= spacetime
DB ?= mt2-yongan-v2
WINDOWS_DB ?= mt2-training-v2
SERVER_URL ?= http://127.0.0.1:3210
LISTEN_ADDR ?= 127.0.0.1:3210
PROFILE ?= default
PLAYER_NAME ?= Warrior
MAP ?= metin2_map_a1
SERVER_FEATURES ?= yongan
SERVER_FEATURE_FLAGS = $(if $(strip $(SERVER_FEATURES)),--features "$(SERVER_FEATURES)",)
INCLUDE_MAP ?= --include-map
TEST_PROBE ?=
PUBLIC_URL ?= https://kcanakdag.com:8443
DEPLOY_HOST ?= root@159.195.213.9
DEPLOY_NAME ?= kcanakdag.com
DEPLOY_PORT ?= 8443
WEB_DIR ?= dist/web
DEPLOY_FLAGS ?=
BROWSER_PYTHON ?= .local/venv-dev/bin/python
UI_FLAGS ?=
BROWSER_FLAGS ?=
AUTH_HOST ?= 127.0.0.1
AUTH_PORT ?= 3219
AUTH_ISSUER ?= http://127.0.0.1:$(AUTH_PORT)/auth
AUTH_DATA_DIR ?= $(CURDIR)/.local/auth
CONTENT_PROFILE ?= content/profiles/p0-warrior-dog.json
WORLD_PROFILE ?= content/worlds/yongan.population.json
WORLD_OUTPUT ?= .local/world-content/$@-$(shell date -u +%Y%m%dT%H%M%SZ)
WORLD_FLAGS ?=
NPC_CONTENT ?= .local/npcs/city-guard
CHARACTER_OUTPUT ?= .local/characters/build-$(shell date -u +%Y%m%dT%H%M%SZ)
CHARACTER_FLAGS ?=
GAME_SERVER_URL ?= $(SERVER_URL)
STORAGE_DATA_DIR ?= .local/p1/server
STORAGE_SERVER ?= http://127.0.0.1:13223
STORAGE_CONFIG ?= .local/p1/cli.toml
STORAGE_KEEP_DAYS ?= 2
STORAGE_BUDGET_GB ?= 8
STORAGE_FLAGS ?=
STORAGE_PYTHON ?= .local/venv-dev/bin/python
STORAGE_CLEAN_DIR := .local/maintenance/storage-clean-$(shell date -u +%Y%m%dT%H%M%SZ)
STORAGE_MANIFEST ?= $(STORAGE_CLEAN_DIR)/detached.json
STORAGE_ORPHAN_MANIFEST ?= .local/maintenance/storage-sweep-orphans.json

.PHONY: assets import-assets import-map import-ui content-build content-validate content-probe test-ui test-actors test-inventory bake-map map-preview test-map test-world-packs editor client preview check server-build server-test server-start server-publish mcp-build mcp-check dev-setup lint format bindings test-tools test-multiplayer test-combat export-windows export-web export-linux browser-setup test-browser deploy share-setup share-start share-status share-stop export-shared
.PHONY: auth-setup auth-start test-auth test-accounts test-physical
.PHONY: check-plan
.PHONY: world-validate world-preview npc-install test-npcs
.PHONY: characters-build test-classes skills-build dummy-build
.PHONY: storage-report storage-entries storage-files storage-clean storage-sweep

dummy-build:
	python3 tools/build_training_dummy.py --blender "$(BLENDER)" --install

skills-build:
	python3 tools/build_skill_catalog.py --offline

characters-build:
	python3 tools/import_character_content.py --blender "$(BLENDER)" --output "$(CHARACTER_OUTPUT)" --install $(CHARACTER_FLAGS)

test-classes:
	python3 tools/test_physical_combat.py --server "$(SERVER_URL)" --game-server "$(GAME_SERVER_URL)" --database "$(DB)" --scenario classes --godot "$(GODOT)" --report "$(CHARACTER_OUTPUT)/two-client.json"

assets:
	python3 tools/fetch_test_assets.py

import-assets:
	$(BLENDER) --background --python-exit-code 1 --python tools/blender_import_probe.py

import-map:
	python3 tools/import_metin_map.py --map "$(MAP)" --blender "$(BLENDER)" --godot "$(GODOT)"

bake-map:
	test "$(MAP)" = "metin2_map_a1"
	$(BLENDER) --background --factory-startup -noaudio --python-exit-code 1 --python tools/bake_yongan.py
	XDG_DATA_HOME="$(CURDIR)/.local/map-check/data" XDG_CONFIG_HOME="$(CURDIR)/.local/map-check/config" $(GODOT) --headless --path client --script "$(CURDIR)/tools/build_metin_map.gd" -- "$(MAP)"

map-preview:
	$(GODOT) --path client res://scenes/map_preview.tscn -- --map "$(MAP)"

world-validate:
	python3 tools/world_content.py validate --profile "$(WORLD_PROFILE)" --output "$(WORLD_OUTPUT)"

world-preview:
	python3 tools/world_content.py preview --profile "$(WORLD_PROFILE)" --output "$(WORLD_OUTPUT)" --godot "$(GODOT)" $(WORLD_FLAGS)

npc-install:
	python3 tools/build_npc_catalog.py --content "$(NPC_CONTENT)" --population "$(WORLD_PROFILE)" --output "$(WORLD_OUTPUT)" --install

test-npcs:
	python3 tools/test_world_npcs.py --godot "$(GODOT)" --native --output "$(WORLD_OUTPUT)"

test-map:
	python3 -m unittest discover -s tests -p 'test_metin_map.py'
	XDG_DATA_HOME="$(CURDIR)/.local/map-check/data" XDG_CONFIG_HOME="$(CURDIR)/.local/map-check/config" $(GODOT) --headless --path client --script "$(CURDIR)/tools/check_metin_map.gd" -- "$(MAP)"

editor:
	$(GODOT) --path client --editor res://scenes/main.tscn

client:
	$(GODOT) --path client -- --server "$(SERVER_URL)" --database "$(DB)" --profile "$(PROFILE)" --name "$(PLAYER_NAME)"

preview:
	$(GODOT) --path client res://scenes/character_preview.tscn

server-build:
	cargo build --manifest-path server/Cargo.toml --locked --no-default-features $(SERVER_FEATURE_FLAGS) --target wasm32-unknown-unknown --release

server-test:
	cargo test --manifest-path server/Cargo.toml --locked --no-default-features $(SERVER_FEATURE_FLAGS)

server-start:
	$(SPACETIME) start --listen-addr "$(LISTEN_ADDR)" --data-dir "$(CURDIR)/.local/spacetimedb" --non-interactive

auth-setup:
	npm --prefix auth ci

auth-start:
	npm --prefix auth run build
	AUTH_HOST="$(AUTH_HOST)" AUTH_PORT="$(AUTH_PORT)" AUTH_ISSUER="$(AUTH_ISSUER)" AUTH_DATA_DIR="$(abspath $(AUTH_DATA_DIR))" npm --prefix auth start

test-auth:
	npm --prefix auth test

test-accounts:
	python3 tools/test_accounts.py --godot "$(GODOT)" --server "$(SERVER_URL)" --database "$(DB)" --report .local/accounts-report.json

test-physical:
	python3 tools/test_physical_combat.py --godot "$(GODOT)" --server "$(SERVER_URL)" --database "$(DB)" --report .local/p2-physical/combat-report.json

server-publish: server-build
	$(SPACETIME) --config-path .local/spacetime-cli.toml publish --server "$(SERVER_URL)" --bin-path server/target/wasm32-unknown-unknown/release/mt2_server.wasm "$(DB)" --no-config

check: lint server-test test-tools test-auth check-plan
	python3 tools/check_client.py --godot $(GODOT)

check-plan:
	python3 tools/check_rebuild_plan.py

test-tools:
	python3 -m unittest discover -s tests -p 'test_*.py'

dev-setup:
	python3 tools/dev.py setup

lint:
	python3 tools/dev.py lint

format:
	python3 tools/dev.py format

bindings:
	python3 tools/generate_bindings.py --godot "$(GODOT)" --server "$(SERVER_URL)" --database "$(DB)"

test-multiplayer:
	python3 tools/test_multiplayer.py --godot "$(GODOT)" --server "$(SERVER_URL)" --database "$(DB)"

test-combat:
	python3 tools/test_multiplayer.py --godot "$(GODOT)" --server "$(SERVER_URL)" --database "$(DB)" --script combat_smoke --report .local/combat-report.json

test-inventory:
	python3 tools/test_multiplayer.py --godot "$(GODOT)" --server "$(SERVER_URL)" --database "$(DB)" --script inventory_smoke --report .local/inventory-report.json

import-ui:
	.local/venv-dev/bin/python tools/import_metin_ui.py

content-build:
	python3 tools/content_compile.py build --profile "$(CONTENT_PROFILE)" --blender "$(BLENDER)"

content-validate:
	python3 tools/content_compile.py validate --profile "$(CONTENT_PROFILE)"

content-probe:
	python3 tools/content_compile.py probe-godot --profile "$(CONTENT_PROFILE)" --godot "$(GODOT)"

test-ui:
	python3 tools/test_classic_ui.py --godot "$(GODOT)" $(UI_FLAGS)

test-actors:
	python3 tools/test_actors.py --godot "$(GODOT)" $(UI_FLAGS)

export-windows:
	.local/venv-dev/bin/python tools/export_client.py --godot "$(GODOT)" --server "$(SERVER_URL)" --database "$(WINDOWS_DB)"

export-web:
	.local/venv-dev/bin/python tools/export_playable.py --target web --godot "$(GODOT)" --server "$(SERVER_URL)" --database "$(DB)" $(INCLUDE_MAP) $(TEST_PROBE)

export-linux:
	.local/venv-dev/bin/python tools/export_playable.py --target linux --godot "$(GODOT)" --server "$(SERVER_URL)" --database "$(DB)" $(INCLUDE_MAP) $(TEST_PROBE)

browser-setup:
	$(BROWSER_PYTHON) -m pip install -r tools/requirements-browser.txt

test-browser:
	$(BROWSER_PYTHON) tools/test_browser.py --url "$(PUBLIC_URL)" --database "$(DB)" $(BROWSER_FLAGS)

test-world-packs:
	python3 tools/check_world_packs.py --godot "$(GODOT)" --world-dir "$(WEB_DIR)/world"

deploy:
	python3 tools/deploy.py --host "$(DEPLOY_HOST)" --public-name "$(DEPLOY_NAME)" --port "$(DEPLOY_PORT)" --database "$(DB)" --web-dir "$(WEB_DIR)" $(DEPLOY_FLAGS)

share-setup:
	python3 tools/share_server.py install

share-start:
	python3 tools/share_server.py start --database "$(DB)"

share-status:
	python3 tools/share_server.py status

share-stop:
	python3 tools/share_server.py stop

export-shared:
	python3 tools/share_server.py export --godot "$(GODOT)"

mcp-build:
	npm --prefix tools/godot-mcp-server ci --ignore-scripts
	npm --prefix tools/godot-mcp-server run build

mcp-check:
	python3 tools/godot_mcp_check.py --smoke

# Local SpacetimeDB replica maintenance. `storage-report` is read-only;
# `storage-clean` deletes obsolete QA database rows, then stops the standalone
# server, removes only the replica directories those rows used, and starts it
# again. Add `STORAGE_FLAGS=--offline` to review sizes without the CLI.
storage-report:
	$(STORAGE_PYTHON) tools/storage_cleanup.py report --data-dir "$(STORAGE_DATA_DIR)" --server "$(STORAGE_SERVER)" --config-path "$(STORAGE_CONFIG)" --keep-days "$(STORAGE_KEEP_DAYS)" --budget-gb "$(STORAGE_BUDGET_GB)" $(STORAGE_FLAGS)

storage-entries:
	$(STORAGE_PYTHON) tools/storage_cleanup.py entries --apply --manifest-out "$(STORAGE_CLEAN_DIR)/detached.json" --data-dir "$(STORAGE_DATA_DIR)" --server "$(STORAGE_SERVER)" --config-path "$(STORAGE_CONFIG)" --keep-days "$(STORAGE_KEEP_DAYS)" $(STORAGE_FLAGS)

storage-files:
	$(STORAGE_PYTHON) tools/storage_cleanup.py files --manifest "$(STORAGE_MANIFEST)" --apply --restart-server --data-dir "$(STORAGE_DATA_DIR)" --server "$(STORAGE_SERVER)" --config-path "$(STORAGE_CONFIG)"

storage-clean: storage-entries
	$(STORAGE_PYTHON) tools/storage_cleanup.py files --manifest "$(STORAGE_CLEAN_DIR)/detached.json" --apply --restart-server --data-dir "$(STORAGE_DATA_DIR)" --server "$(STORAGE_SERVER)" --config-path "$(STORAGE_CONFIG)"

# Unattended sweeps (the weekly cron entry) remove only directories whose
# database entry is already gone, so they can never drop a live database.
# Obsolete named QA databases stay behind the reviewed `storage-clean`.
storage-sweep:
	@mkdir -p .local/maintenance
	@rm -f "$(STORAGE_ORPHAN_MANIFEST)"
	$(STORAGE_PYTHON) tools/storage_cleanup.py report --data-dir "$(STORAGE_DATA_DIR)" --server "$(STORAGE_SERVER)" --config-path "$(STORAGE_CONFIG)" --keep-days "$(STORAGE_KEEP_DAYS)" --budget-gb "$(STORAGE_BUDGET_GB)" --orphan-manifest "$(STORAGE_ORPHAN_MANIFEST)" $(STORAGE_FLAGS)
	@if [ -s "$(STORAGE_ORPHAN_MANIFEST)" ]; then \
		$(STORAGE_PYTHON) tools/storage_cleanup.py files --manifest "$(STORAGE_ORPHAN_MANIFEST)" --apply --restart-server --data-dir "$(STORAGE_DATA_DIR)" --server "$(STORAGE_SERVER)" --config-path "$(STORAGE_CONFIG)"; \
		rm -f "$(STORAGE_ORPHAN_MANIFEST)"; \
	else \
		echo "storage-sweep: no orphan replica directories"; \
	fi
