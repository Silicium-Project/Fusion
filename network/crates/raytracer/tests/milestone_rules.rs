//! Behaviour of the milestone commitment and of the probabilistic check:
//! how rows are grouped, which milestone changes when a pixel is altered, how
//! many milestones a worker's reputation costs, and when a check escalates.
//!
//! These rules used to be tested on the Python implementation
//! (`tests/test_raytracer_milestones.py`), removed once the Rust binary became
//! the only one; exact values are also pinned by `python_parity.rs`.

use silicium_raytracer::pipeline::{milestones, ppm, sampling};

/// P6 image of `width` x `height` whose raster is `pixels`.
fn image(width: usize, height: usize, pixels: &[u8]) -> Vec<u8> {
    ppm::encode(width, height, pixels)
}

/// Image whose row `y` is filled with the byte value `y`.
fn striped(width: usize, height: usize) -> Vec<u8> {
    let pixels: Vec<u8> = (0..height)
        .flat_map(|row| vec![row as u8; width * 3])
        .collect();
    image(width, height, &pixels)
}

/// The verifier reads the manifest as JSON, like the orchestrator sends it.
fn as_sampled(manifest: &milestones::MilestoneManifest) -> sampling::SampledManifest {
    serde_json::from_value(serde_json::to_value(manifest).unwrap()).unwrap()
}

#[test]
fn milestones_partition_rows_and_keep_the_tile_position() {
    let manifest = milestones::build(&striped(2, 5), 100, 2, 40).unwrap();

    assert_eq!(manifest.strategy, milestones::STRATEGY);
    assert_eq!(
        (manifest.fragment_x_start, manifest.fragment_x_end),
        (40, 42)
    );
    assert_eq!(
        (manifest.fragment_y_start, manifest.fragment_y_end),
        (100, 105)
    );
    assert_eq!(manifest.milestone_count, 3);
    let rows: Vec<(usize, usize)> = manifest
        .milestones
        .iter()
        .map(|item| (item.y_start, item.y_end))
        .collect();
    assert_eq!(rows, vec![(100, 102), (102, 104), (104, 105)]);
    assert!(manifest
        .milestones
        .iter()
        .all(|item| (item.x_start, item.x_end) == (40, 42)));
}

#[test]
fn altering_a_pixel_changes_only_its_milestone_and_the_commitment() {
    let (width, height) = (2, 6);
    let mut pixels: Vec<u8> = (0..width * height * 3).map(|value| value as u8).collect();
    let original = milestones::build(&image(width, height, &pixels), 0, 2, 0).unwrap();
    pixels[2 * width * 3 + 1] ^= 0xFF; // first row of the second block
    let tampered = milestones::build(&image(width, height, &pixels), 0, 2, 0).unwrap();

    let changed: Vec<usize> = original
        .milestones
        .iter()
        .zip(&tampered.milestones)
        .filter(|(before, after)| before.pixel_sha256 != after.pixel_sha256)
        .map(|(before, _)| before.index)
        .collect();
    assert_eq!(changed, vec![1]);
    assert_ne!(original.commitment_hash, tampered.commitment_hash);
}

#[test]
fn sampling_rate_decreases_with_reputation() {
    assert_eq!(sampling::sampling_rate(0.0), 1.0);
    assert_eq!(sampling::sampling_rate(50.0), 0.6);
    assert_eq!(sampling::sampling_rate(100.0), 0.2);
    assert_eq!(sampling::sampling_rate(150.0), 0.2);
}

#[test]
fn selection_depends_only_on_the_seed() {
    let indexes: Vec<usize> = (0..10).collect();

    let first = sampling::select(&indexes, "nonce-12345", 0.3);
    let again = sampling::select(&indexes, "nonce-12345", 0.3);
    let other_seed = sampling::select(&indexes, "nonce-99999", 0.3);

    assert_eq!(first.len(), 3);
    assert_eq!(first, again);
    assert_ne!(first, other_seed);
}

#[test]
fn detection_probability_follows_sampling_without_replacement() {
    assert_eq!(sampling::detection_probability(10, 0, 3), 0.0);
    assert_eq!(sampling::detection_probability(10, 1, 3), 0.3);
    assert_eq!(sampling::detection_probability(10, 5, 3), 0.9167);
    assert_eq!(sampling::detection_probability(10, 1, 10), 1.0);
}

#[test]
fn verification_passes_on_the_committed_tile_and_escalates_on_tampering() {
    let (width, height) = (2, 10);
    let mut pixels: Vec<u8> = (0..width * height * 3).map(|value| value as u8).collect();
    let clean = image(width, height, &pixels);
    let manifest = as_sampled(&milestones::build(&clean, 0, 2, 0).unwrap());

    let result = sampling::verify(&clean, &manifest, "seed-abc", 100.0).unwrap();
    assert!(result.verified);
    assert!(!result.escalated_to_full);

    pixels[0] ^= 0xFF;
    // Reputation 0 checks every milestone, so the altered one is always sampled.
    let result =
        sampling::verify(&image(width, height, &pixels), &manifest, "seed-abc", 0.0).unwrap();
    assert!(!result.verified);
    assert!(result.escalated_to_full);
    assert_eq!(result.failed_milestones.len(), 1);
    assert_eq!(result.failed_milestones[0].index, 0);
}
