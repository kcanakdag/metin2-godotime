#[path = "../build_training.rs"]
mod build_training;

#[test]
fn build_authored_training_definition() {
    assert!(build_training::build().contains("TrainingTargetDefinition"));
}
