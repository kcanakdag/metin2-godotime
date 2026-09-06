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

.PHONY: assets import-assets import-map import-ui test-ui test-inventory bake-map map-preview test-map test-world-packs editor client preview check server-build server-test server-start server-publish mcp-build mcp-check dev-setup lint format bindings test-tools test-multiplayer test-combat export-windows export-web export-linux browser-setup test-browser deploy share-setup share-start share-status share-stop export-shared

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

server-publish: server-build
	$(SPACETIME) --config-path .local/spacetime-cli.toml publish --server "$(SERVER_URL)" --bin-path server/target/wasm32-unknown-unknown/release/mt2_server.wasm "$(DB)" --no-config

check: lint server-test test-tools
	python3 tools/check_client.py --godot $(GODOT)

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

test-ui:
	python3 tools/test_classic_ui.py --godot "$(GODOT)" $(UI_FLAGS)

export-windows:
	python3 tools/export_client.py --godot "$(GODOT)" --server "$(SERVER_URL)" --database "$(WINDOWS_DB)"

export-web:
	python3 tools/export_playable.py --target web --godot "$(GODOT)" --server "$(SERVER_URL)" --database "$(DB)" $(INCLUDE_MAP) $(TEST_PROBE)

export-linux:
	python3 tools/export_playable.py --target linux --godot "$(GODOT)" --server "$(SERVER_URL)" --database "$(DB)" $(INCLUDE_MAP) $(TEST_PROBE)

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
