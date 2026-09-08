#[path = "../src/regeneration.rs"]
mod regeneration;
use regeneration::EntryState;

#[test]
fn restored_entry_keeps_deadline_and_retired_owner_high_water_mark() {
    let mut state = EntryState::new(5, 1, 2)
        .unwrap()
        .plan_tick(10, || Ok(Some(42)))
        .unwrap();
    state.owner_destroyed(42);
    let restored = EntryState::restore(5, 1, 2, state.snapshot()).unwrap();
    assert_eq!(state, restored);
    let due = restored.next_tick_us().unwrap();
    assert_eq!(
        restored
            .plan_tick(due - 1, || panic!("early refill"))
            .unwrap(),
        restored
    );
    assert!(restored.plan_tick(due, || Ok(Some(42))).is_err());
    let mut next = restored.plan_tick(due, || Ok(Some(43))).unwrap();
    assert!(!next.owner_destroyed(42));
    assert_eq!(next.next_tick_us(), Some(due + 5)); // no repeated startup jitter
}

#[test]
fn restored_state_rejects_duplicates_bad_tokens_deadlines_and_disabled_owners() {
    let state = EntryState::new(5, 2, 0)
        .unwrap()
        .plan_tick(10, || Ok(None))
        .unwrap();
    for owners in [vec![0], vec![1, 1], vec![2, 1], vec![3], vec![1, 2, 3]] {
        let mut saved = state.snapshot();
        saved.last_owner = 2;
        saved.owners = owners;
        assert!(EntryState::restore(5, 2, 0, saved).is_err());
    }
    for deadline in [None, Some(-1), Some(4)] {
        let mut saved = state.snapshot();
        saved.next_tick_us = deadline;
        assert!(EntryState::restore(5, 2, 0, saved).is_err());
    }
    assert!(EntryState::restore(0, 2, 0, state.snapshot()).is_err());
    let mut saved = state.snapshot();
    saved.initial = true;
    assert!(EntryState::restore(5, 2, 0, saved).is_err());
    let disabled = EntryState::new(0, 2, 0).unwrap();
    assert_eq!(
        EntryState::restore(0, 2, 0, disabled.snapshot()).unwrap(),
        disabled
    );
}

#[test]
fn leader_destruction_releases_one_unit_without_followers_or_immediate_respawn() {
    let state = EntryState::new(5_000_000, 1, 3).unwrap();
    let mut state = state.plan_tick(10_000_000, || Ok(Some(100))).unwrap();
    assert_eq!(state.next_tick_us(), Some(18_000_000));
    assert!(!state.owner_destroyed(101)); // Surviving/destroyed follower owns no capacity.
    assert_eq!(state.owners().len(), 1);
    assert!(state.owner_destroyed(100));
    assert!(!state.owner_destroyed(100));
    assert!(state.plan_tick(18_000_000, || Ok(Some(100))).is_err());
    let state = state.plan_tick(17_999_999, || panic!("not due")).unwrap();
    let mut state = state.plan_tick(18_000_000, || Ok(Some(200))).unwrap();
    assert!(!state.owner_destroyed(100)); // Stale cleanup cannot destroy a replacement life.
    assert_eq!(
        state.owners().iter().copied().collect::<Vec<_>>(),
        vec![200]
    );
    assert_eq!(state.next_tick_us(), Some(23_000_000));
}

#[test]
fn failed_placements_retry_on_next_tick_and_late_ticks_do_not_burst() {
    let state = EntryState::new(5, 3, 0).unwrap();
    let mut attempts = 0;
    let state = state
        .plan_tick(0, || {
            attempts += 1;
            Ok(if attempts == 2 { Some(10) } else { None })
        })
        .unwrap();
    assert_eq!(attempts, 3);
    let mut ids = [20, 30].into_iter();
    let state = state
        .plan_tick(100, || Ok(Some(ids.next().unwrap())))
        .unwrap();
    assert_eq!(state.owners().len(), 3);
    assert_eq!(state.next_tick_us(), Some(105));
    assert!(ids.next().is_none());
    let state = state.plan_tick(105, || panic!("full entry")).unwrap();
    assert_eq!(state.next_tick_us(), Some(110));
}

#[test]
fn disabled_entries_never_spawn_and_bad_callbacks_leave_state_unchanged() {
    let disabled = EntryState::new(0, 3, 0).unwrap();
    assert_eq!(
        disabled.plan_tick(0, || panic!("disabled")).unwrap(),
        disabled
    );
    let state = EntryState::new(5, 2, 0).unwrap();
    assert!(state.plan_tick(0, || Ok(Some(1))).is_err()); // duplicate second owner
    assert!(state.plan_tick(0, || Ok(Some(0))).is_err());
    assert!(state.plan_tick(0, || Err("spawn failed".into())).is_err());
    assert!(state.owners().is_empty());
    assert_eq!(state.next_tick_us(), None);
    assert!(
        state
            .plan_tick(i64::MAX, || panic!("overflow before spawn"))
            .is_err()
    );
    assert!(EntryState::new(-1, 1, 0).is_err());
    assert!(EntryState::new(5, 1001, 0).is_err());
}
