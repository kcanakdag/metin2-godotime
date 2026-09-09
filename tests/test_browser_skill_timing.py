"""Validate measurement boundaries independently of the game renderer."""

import json
import shutil
import subprocess
import unittest

from tools.browser_skill_timing import INSTALL_SKILL_TIMING_JS


class BrowserSkillTimingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is required for browser timing semantics")
    def test_first_matching_observations_and_input_are_retained(self):
        script = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const listeners = {};
let tick = 0;
const window = {addEventListener: (name, fn) => listeners[name] = fn};
const context = vm.createContext({window, performance: {timeOrigin: 1000, now: () => tick}});
vm.runInContext(JSON.parse(fs.readFileSync(0, 'utf8')), context);
window.mt2ArmSkillTiming({key:'1', owner:'owner', sequence:4, vnum:5,
    target:9, life:2, health:100, effects:0});
window.mt2Snapshot = '{}';
tick = 1; listeners.keydown({key:'1', repeat:true});
assert.equal(window.mt2SkillTiming.input_epoch_ms, null);
tick = 2; listeners.keydown({key:'1', repeat:false});
tick = 3; listeners.keydown({key:'1', repeat:false});
assert.equal(window.mt2SkillTiming.input_epoch_ms, 1002);
const state = {player_rows:[{identity:'other',attack_sequence:5,attack_action_id:'x.skill_5'}],
    monsters:[{id:9,life_sequence:3,health:90}],motion_effects:{spawned:0}};
window.mt2Snapshot = JSON.stringify(state);
assert.equal(window.mt2SkillTiming.action_epoch_ms, null);
assert.equal(window.mt2SkillTiming.damage_epoch_ms, null);
state.player_rows[0].identity = 'owner';
state.monsters[0].life_sequence = 2;
state.motion_effects.spawned = 1;
tick = 7; window.mt2Snapshot = JSON.stringify(state);
tick = 9; window.mt2Snapshot = JSON.stringify(state);
assert.equal(window.mt2SkillTiming.action_epoch_ms, 1007);
assert.equal(window.mt2SkillTiming.damage_epoch_ms, 1007);
assert.equal(window.mt2SkillTiming.effect_epoch_ms, 1007);
assert.equal(window.mt2Snapshot, JSON.stringify(state));
window.mt2Snapshot = '';
assert.equal(window.mt2SkillTiming.action_epoch_ms, 1007);
"""
        subprocess.run(
            [shutil.which("node"), "-e", script],
            input=json.dumps(INSTALL_SKILL_TIMING_JS),
            text=True,
            check=True,
            capture_output=True,
            timeout=10,
        )
