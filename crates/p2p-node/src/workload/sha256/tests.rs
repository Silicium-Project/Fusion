//! sha256 workload: chunking, hashing, checks and assembly.

use super::*;
use std::collections::BTreeMap;

fn settings(max_fragments: usize, target_bytes: usize) -> JobSettings {
    JobSettings {
        max_fragments,
        target_bytes,
        ..JobSettings::default()
    }
}

fn temp_file(name: &str, bytes: &[u8]) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("silicium-sha256-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join(name);
    std::fs::write(&path, bytes).unwrap();
    path
}

fn task() -> NetworkTask {
    NetworkTask {
        task_id: format!("{}.hash", "a".repeat(32)),
        root_job_id: Some("site-1".into()),
        scene_path: "content/input".into(),
        output_path: String::new(),
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
        workload: Some(ID.into()),
        solana_payment: None,
        byte_range: None,
        requested_fragment_count: None,
    }
}

#[test]
fn chunks_cover_the_input_once() {
    for (size, requested, max, target) in [
        (0u64, None, 8, 4),
        (1, None, 8, 4),
        (10, None, 8, 4),
        (10, Some(3), 8, 4),
        (10, Some(50), 8, 4),
        (1000, None, 4, 10),
    ] {
        let ranges = chunk_ranges(size, requested, &settings(max, target));
        assert!(!ranges.is_empty());
        assert!(ranges.len() <= requested.unwrap_or(max).max(1));
        assert_eq!(ranges[0].start, 0);
        assert_eq!(ranges.last().unwrap().end, size);
        assert!(ranges.windows(2).all(|pair| pair[0].end == pair[1].start));
    }
    assert_eq!(chunk_ranges(10, None, &settings(8, 4)).len(), 3);
    assert_eq!(chunk_ranges(10, Some(3), &settings(8, 4)).len(), 3);
    assert_eq!(
        chunk_ranges(3, Some(8), &settings(8, 4)).len(),
        3,
        "one byte per chunk at most"
    );
}

/// Same digest as the Python handler (`hashlib.sha256(data).hexdigest()`).
#[test]
fn a_whole_input_hashes_like_the_python_handler() {
    let path = temp_file("abc", b"abc");
    let chunk = hash_chunk(&path, None, 0).unwrap();
    assert_eq!(
        chunk.sha256,
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
    assert_eq!((chunk.offset, chunk.length), (0, 3));
    let middle = hash_chunk(&path, Some(ByteRange { start: 1, end: 2 }), 1).unwrap();
    assert_eq!(middle.sha256, sha256_hex(b"b"));
    assert!(hash_chunk(&path, Some(ByteRange { start: 0, end: 4 }), 0).is_err());
}

#[test]
fn a_task_is_split_into_chunk_tasks() {
    let path = temp_file("ten", b"0123456789");
    let (manifest, tasks) = Sha256.split(&task(), &path, &settings(8, 4)).unwrap();
    assert_eq!(manifest.workload, ID);
    assert_eq!(manifest.input_bytes, 10);
    assert_eq!(tasks.len(), 3);
    for (index, fragment) in tasks.iter().enumerate() {
        assert_eq!(fragment.task_id, fragment_task_id(&task().task_id, index));
        assert_eq!(fragment.workload.as_deref(), Some(ID));
        assert_eq!(fragment.byte_range, manifest.fragments[index].byte_range);
        assert_eq!(
            fragment.output_path,
            format!("{}/output.bin", fragment.task_id)
        );
    }
    let already = NetworkTask {
        byte_range: Some(ByteRange { start: 0, end: 2 }),
        ..task()
    };
    assert!(Sha256.split(&already, &path, &settings(8, 4)).is_none());
}

#[test]
fn the_job_result_lists_every_chunk() {
    let data = b"0123456789";
    let path = temp_file("job", data);
    let (manifest, tasks) = Sha256.split(&task(), &path, &settings(8, 4)).unwrap();
    let fragments: Vec<Vec<u8>> = tasks
        .iter()
        .enumerate()
        .map(|(index, fragment)| {
            let chunk = hash_chunk(&path, fragment.byte_range, index as u32).unwrap();
            serde_json::to_vec(&chunk).unwrap()
        })
        .collect();
    for (fragment, bytes) in manifest.fragments.iter().zip(&fragments) {
        assert!(Sha256.accepts_result(Some(fragment), bytes, &[]));
    }
    assert!(
        !Sha256.accepts_result(Some(&manifest.fragments[0]), &fragments[1], &[]),
        "chunk of another range"
    );
    assert!(!Sha256.accepts_result(None, b"not json", &[]));

    let outputs = Sha256
        .assemble(&manifest, Path::new(""), &fragments)
        .unwrap();
    let result: JobHash = serde_json::from_slice(&outputs[0].bytes).unwrap();
    assert_eq!(result.size_bytes, 10);
    assert_eq!(result.chunk_count, 3);
    assert_eq!(result.chunks[1].sha256, sha256_hex(b"4567"));
    assert_eq!(result.input_hash, None, "several chunks");
    let list: String = result
        .chunks
        .iter()
        .map(|c| format!("{}\n", c.sha256))
        .collect();
    assert_eq!(result.chunk_list_sha256, sha256_hex(list.as_bytes()));

    assert!(
        Sha256
            .assemble(&manifest, Path::new(""), &fragments[..2])
            .is_err(),
        "a chunk is missing"
    );
}

#[test]
fn a_single_chunk_job_reports_the_input_hash() {
    let path = temp_file("one", b"abc");
    let (manifest, tasks) = Sha256.split(&task(), &path, &settings(8, 1024)).unwrap();
    assert_eq!(tasks.len(), 1);
    let chunk = hash_chunk(&path, tasks[0].byte_range, 0).unwrap();
    let outputs = Sha256
        .assemble(
            &manifest,
            Path::new(""),
            &[serde_json::to_vec(&chunk).unwrap()],
        )
        .unwrap();
    let result: JobHash = serde_json::from_slice(&outputs[0].bytes).unwrap();
    assert_eq!(
        result.input_hash.as_deref(),
        Some(sha256_hex(b"abc").as_str())
    );
}
