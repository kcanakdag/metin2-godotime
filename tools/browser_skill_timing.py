"""Browser-side observation timing; this never sends gameplay actions."""

INSTALL_SKILL_TIMING_JS = r"""
(() => {
    let value = window.mt2Snapshot;
    let armed = null;
    const now = () => performance.timeOrigin + performance.now();
    window.mt2ArmSkillTiming = config => {
        armed = config;
        window.mt2SkillTiming = {input_epoch_ms: null, action_epoch_ms: null,
            damage_epoch_ms: null, effect_epoch_ms: null};
    };
    window.addEventListener('keydown', event => {
        if (armed && event.key === armed.key && !event.repeat
                && window.mt2SkillTiming.input_epoch_ms === null) {
            window.mt2SkillTiming.input_epoch_ms = now();
        }
    }, true);
    Object.defineProperty(window, 'mt2Snapshot', {
        configurable: true,
        get: () => value,
        set: next => {
            value = next;
            if (!armed) return;
            let state;
            try { state = JSON.parse(next || '{}'); } catch (_) { return; }
            const time = now();
            const result = window.mt2SkillTiming;
            const actor = (state.player_rows || []).find(row => row.identity === armed.owner);
            if (actor && actor.attack_sequence > armed.sequence
                    && String(actor.attack_action_id).endsWith('.skill_' + armed.vnum)
                    && result.action_epoch_ms === null) result.action_epoch_ms = time;
            const target = (state.monsters || []).find(row => row.id === armed.target);
            if (target && target.life_sequence === armed.life && target.health < armed.health
                    && result.damage_epoch_ms === null) result.damage_epoch_ms = time;
            if ((state.motion_effects || {}).spawned > armed.effects
                    && result.effect_epoch_ms === null) result.effect_epoch_ms = time;
        }
    });
})();
"""
