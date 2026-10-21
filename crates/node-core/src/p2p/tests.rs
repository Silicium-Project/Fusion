//! Tests of the peer envelopes: record keys, remote task sanitizing.

use super::*;

#[test]
fn hardware_record_key_is_versioned() {
    assert_eq!(
        DhtRecordEnvelope::hardware_record_key("peer-123"),
        "silicium/hardware/v1/peer-123"
    );
}

#[test]
fn task_record_key_is_versioned() {
    assert_eq!(
        DhtRecordEnvelope::task_record_key("task-456"),
        "silicium/task/v1/task-456"
    );
}

#[test]
fn task_event_record_key_is_content_addressed() {
    let key = DhtRecordEnvelope::task_event_key(&"a".repeat(64));
    assert_eq!(key, format!("silicium/taskbook/v1/{}", "a".repeat(64)));
}

fn remote_task() -> TaskEnvelope {
    TaskEnvelope {
        task_id: "job-1-frag-000".to_string(),
        scene_path: "scenes/demo.cfg".to_string(),
        output_path: "/etc/passwd".to_string(),
        seed: "7".to_string(),
        hardware_hint: None,
        runtime_hint: None,
        runtime_args: vec!["--flag".to_string()],
        runtime_env: BTreeMap::from([("LD_PRELOAD".to_string(), "/tmp/evil.so".to_string())]),
        runtime_workdir: Some(PathBuf::from("/")),
        runtime_module_path: None,
        runtime_image: None,
        scene_sha256: Some("not-a-hash".to_string()),
        region: None,
        workload: None,
        solana_payment: None,
        byte_range: None,
    }
}

#[test]
fn workload_ids_are_checked() {
    for good in ["raytracer", "calcul/integrity/sha256", "a.b_c-d/e1"] {
        assert!(is_valid_workload_id(good), "{good}");
    }
    for bad in [
        "",
        "Raytracer",
        "a//b",
        "../x",
        "a/./b",
        "a b",
        &"x".repeat(81),
    ] {
        assert!(!is_valid_workload_id(bad), "{bad}");
    }
}

#[test]
fn a_workload_and_a_byte_range_are_kept_when_valid() {
    let range = ByteRange { start: 4, end: 9 };
    let task = TaskEnvelope {
        workload: Some("calcul/integrity/sha256".to_string()),
        byte_range: Some(range),
        ..remote_task()
    };
    let clean = task.sanitize_remote(&RemoteTaskPolicy::default()).unwrap();
    assert_eq!(clean.workload.as_deref(), Some("calcul/integrity/sha256"));
    assert_eq!(clean.byte_range, Some(range));
    assert_eq!(clean.output_path, "job-1-frag-000/output.bin");

    let bad_workload = TaskEnvelope {
        workload: Some("../evil".to_string()),
        ..remote_task()
    };
    assert_eq!(
        bad_workload.sanitize_remote(&RemoteTaskPolicy::default()),
        Err(RemoteTaskError::InvalidWorkload)
    );
    let bad_range = TaskEnvelope {
        byte_range: Some(ByteRange { start: 9, end: 4 }),
        ..remote_task()
    };
    assert_eq!(
        bad_range.sanitize_remote(&RemoteTaskPolicy::default()),
        Err(RemoteTaskError::InvalidByteRange)
    );
}

#[test]
fn an_envelope_without_workload_keeps_its_former_encoding() {
    let json = serde_json::to_value(remote_task()).unwrap();
    assert!(json.get("workload").is_none() && json.get("byte_range").is_none());
}

#[test]
fn a_region_is_kept_only_when_valid() {
    let region = Region {
        x_start: 0,
        x_end: 10,
        y_start: 5,
        y_end: 9,
    };
    let task = TaskEnvelope {
        region: Some(region),
        ..remote_task()
    };
    let clean = task.sanitize_remote(&RemoteTaskPolicy::default()).unwrap();
    assert_eq!(clean.region, Some(region));
    for bad in [
        Region {
            x_start: 3,
            x_end: 3,
            ..region
        },
        Region {
            y_start: 9,
            y_end: 5,
            ..region
        },
        Region {
            x_end: Region::MAX_SIDE + 1,
            ..region
        },
    ] {
        let task = TaskEnvelope {
            region: Some(bad),
            ..remote_task()
        };
        assert_eq!(
            task.sanitize_remote(&RemoteTaskPolicy::default()),
            Err(RemoteTaskError::InvalidRegion)
        );
    }
}

#[test]
fn remote_tasks_lose_the_fields_a_peer_must_not_control() {
    let clean = remote_task()
        .sanitize_remote(&RemoteTaskPolicy::default())
        .unwrap();
    assert_eq!(clean.output_path, "job-1-frag-000/output.ppm");
    assert!(clean.runtime_env.is_empty());
    assert!(clean.runtime_workdir.is_none());
    assert!(clean.runtime_args.is_empty());
    assert!(clean.runtime_envelope("peer").is_none());
    assert!(clean.scene_sha256.is_none(), "malformed scene hash dropped");
}

#[test]
fn remote_tasks_cannot_pick_host_paths_or_docker_images() {
    let policy = RemoteTaskPolicy::default();
    for scene in ["../secret.cfg", "/etc/passwd", "C:\\Windows\\win.ini", ""] {
        let task = TaskEnvelope {
            scene_path: scene.to_string(),
            ..remote_task()
        };
        assert!(
            matches!(
                task.sanitize_remote(&policy),
                Err(RemoteTaskError::InvalidPath(_))
            ),
            "{scene}"
        );
    }
    let docker = TaskEnvelope {
        runtime_image: Some("evil:latest".to_string()),
        ..remote_task()
    };
    assert_eq!(
        docker.sanitize_remote(&policy),
        Err(RemoteTaskError::OciRefused)
    );
    let bad_id = TaskEnvelope {
        task_id: "../x".to_string(),
        ..remote_task()
    };
    assert_eq!(
        bad_id.sanitize_remote(&policy),
        Err(RemoteTaskError::InvalidTaskId)
    );
}

#[test]
fn remote_wasm_needs_an_explicit_policy_and_a_sandboxed_module() {
    let wasm = TaskEnvelope {
        runtime_module_path: Some(PathBuf::from("modules/job.wasm")),
        ..remote_task()
    };
    assert_eq!(
        wasm.sanitize_remote(&RemoteTaskPolicy::default()),
        Err(RemoteTaskError::WasmRefused)
    );
    let allowed = wasm
        .sanitize_remote(&RemoteTaskPolicy { allow_wasm: true })
        .unwrap();
    assert_eq!(allowed.runtime_hint.as_deref(), Some("wasm"));
    assert!(allowed.runtime_env.is_empty());
    let escaping = TaskEnvelope {
        runtime_module_path: Some(PathBuf::from("../x.wasm")),
        ..remote_task()
    };
    assert!(
        escaping
            .sanitize_remote(&RemoteTaskPolicy { allow_wasm: true })
            .is_err()
    );
}
