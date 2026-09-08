#[path = "../src/monster_allocation.rs"]
mod monster_allocation;
use monster_allocation::reserve;

#[test]
fn replacement_never_reuses_destroyed_leader_or_surviving_follower_ids() {
    // Authored mobs and dummy occupy IDs through 900001.
    let original = reserve(900001, 3).unwrap();
    assert_eq!(
        (original.first, original.last, original.owner()),
        (900002, 900004, 900002)
    );
    // The leader is destroyed, both followers survive. Keep the allocation
    // high-water mark; it is not the count of currently live owners/entities.
    let replacement = reserve(original.last, 4).unwrap();
    assert_eq!((replacement.first, replacement.last), (900005, 900008));
    assert!(replacement.first > original.last);
    assert_ne!(original.owner(), replacement.owner());
    // A partial placement allocates only successfully placed members.
    let partial = reserve(replacement.last, 1).unwrap();
    assert_eq!((partial.first, partial.last), (900009, 900009));
}

#[test]
fn overflow_or_invalid_group_size_rejects_without_wrapping_or_partial_reservation() {
    assert!(reserve(0, 0).is_err());
    assert!(reserve(0, 257).is_err());
    assert!(reserve(u32::MAX, 1).is_err());
    assert!(reserve(u32::MAX - 2, 3).is_err());
    let last_group = reserve(u32::MAX - 2, 2).unwrap();
    assert_eq!(last_group.last, u32::MAX);
    assert_eq!(last_group.owner(), u64::from(u32::MAX - 1));
    assert!(reserve(last_group.last, 1).is_err());
}
