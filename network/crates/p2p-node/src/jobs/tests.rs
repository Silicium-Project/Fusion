//! Splitting a job into fragments, the manifest store, and reassembly.

use super::*;
use crate::{task::NetworkTask, workload::raytracer::split_scene as split};
use silicium_node_core::p2p::Region;
use silicium_node_core::taskbook::TaskEvent;
use silicium_raytracer::pipeline::ppm;
use std::collections::BTreeMap;

const SCENE: &str = "camera : { resolution = { width = 64 height = 48 } }";

fn task() -> NetworkTask {
    NetworkTask {
        task_id: format!("{}.job", "a".repeat(32)),
        root_job_id: None,
        parent_task_id: None,
        scene_path: "content/scene".into(),
        output_path: "x/output.ppm".into(),
        seed: "1".into(),
        hardware_hint: None,
        runtime_hint: None,
        runtime_args: Vec::new(),
        runtime_env: BTreeMap::new(),
        runtime_workdir: None,
        runtime_module_path: None,
        runtime_image: None,
        scene_sha256: Some("b".repeat(64)),
        region: None,
        workload: None,
        solana_payment: None,
        byte_range: None,
        requested_fragment_count: None,
        delegation_depth: 0,
    }
}

fn settings() -> JobSettings {
    JobSettings {
        max_fragments: 8,
        target_pixels: 500,
        ..JobSettings::default()
    }
}

/// Deterministic full image; a fragment is its crop.
fn full_image(width: usize, height: usize) -> Vec<u8> {
    (0..width * height * 3)
        .map(|i| (i * 7 % 253) as u8)
        .collect()
}

fn crop(pixels: &[u8], width: usize, region: Region) -> Vec<u8> {
    let mut out = Vec::new();
    for y in region.y_start as usize..region.y_end as usize {
        let row = y * width * 3;
        out.extend_from_slice(
            &pixels[row + region.x_start as usize * 3..row + region.x_end as usize * 3],
        );
    }
    ppm::encode(
        (region.x_end - region.x_start) as usize,
        (region.y_end - region.y_start) as usize,
        &out,
    )
}

#[test]
fn a_whole_image_task_is_split_into_tiles_covering_the_image_once() {
    let (manifest, tasks) = split(&task(), SCENE, &settings()).unwrap();
    assert_eq!((manifest.width, manifest.height), (64, 48));
    // 64 x 48 pixels at about 500 per fragment: 7 fragments (at most 8).
    assert_eq!(tasks.len(), 7);
    assert_eq!(manifest.fragments.len(), 7);
    let mut covered = vec![0u8; 64 * 48];
    for (index, fragment) in tasks.iter().enumerate() {
        let region = fragment.region.unwrap();
        assert_eq!(manifest.fragments[index].region, region);
        assert_eq!(fragment.task_id, fragment_task_id(&manifest.job_id, index));
        assert!(TaskEvent::is_valid_task_id(&fragment.task_id));
        assert_eq!(
            fragment.output_path,
            format!("{}/output.ppm", fragment.task_id)
        );
        assert_eq!(fragment.scene_sha256, task().scene_sha256);
        for y in region.y_start..region.y_end {
            for x in region.x_start..region.x_end {
                covered[(y * 64 + x) as usize] += 1;
            }
        }
    }
    assert!(covered.iter().all(|count| *count == 1));
}

#[test]
fn a_local_requested_fragment_count_overrides_estimation() {
    let mut requested = task();
    requested.requested_fragment_count = Some(8);
    let (manifest, tasks) = split(&requested, SCENE, &settings()).unwrap();
    assert_eq!(tasks.len(), 8);
    assert_eq!(manifest.fragments.len(), 8);
}

#[test]
fn tasks_with_a_region_or_a_module_are_not_split() {
    let region = Region {
        x_start: 0,
        x_end: 4,
        y_start: 0,
        y_end: 4,
    };
    assert!(
        split(
            &NetworkTask {
                root_job_id: None,
                region: Some(region),
                ..task()
            },
            SCENE,
            &settings()
        )
        .is_none()
    );
    let module = NetworkTask {
        root_job_id: None,
        runtime_module_path: Some("m.wasm".into()),
        ..task()
    };
    assert!(split(&module, SCENE, &settings()).is_none());
}

#[test]
fn fragments_are_reassembled_once_all_images_are_collected() {
    let root = std::env::temp_dir().join(format!("silicium-jobs-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    let store = JobStore::open(root.clone());
    let (manifest, _) = split(&task(), SCENE, &settings()).unwrap();
    let job_id = manifest.job_id.clone();
    store.add(manifest.clone()).unwrap();

    let reopened = JobStore::open(root.clone());
    assert_eq!(reopened.manifest(&job_id), Some(manifest.clone()));
    let (job, fragment) = reopened.fragment(&manifest.fragments[3].task_id).unwrap();
    assert_eq!(
        (job.job_id.as_str(), fragment.region),
        (job_id.as_str(), manifest.fragments[3].region)
    );
    assert!(reopened.fragment("unknown").is_none());

    let pixels = full_image(64, 48);
    let (last, rest) = manifest.fragments.split_last().unwrap();
    for fragment in rest {
        let path = root.join(JobStore::fragment_result_path(&manifest, &fragment.task_id));
        store::write_atomic(&path, &crop(&pixels, 64, fragment.region)).unwrap();
    }
    assert_eq!(store.assemble(&job_id), Ok(None), "one fragment missing");
    assert!(!store.is_assembled(&job_id));
    store::write_atomic(
        &root.join(JobStore::fragment_result_path(&manifest, &last.task_id)),
        &crop(&pixels, 64, last.region),
    )
    .unwrap();
    let path = store.assemble(&job_id).unwrap().unwrap();
    assert_eq!(std::fs::read(path).unwrap(), ppm::encode(64, 48, &pixels));
    assert!(store.is_assembled(&job_id));
    assert_eq!(store.collected(&manifest).len(), manifest.fragments.len());
}
