//! Document-search workload, with the tiny test model: preparation, split,
//! compute, verification, assembly by the job store, and search.

use super::*;
use crate::{
    activity::ActivityLog,
    content::ContentStore,
    jobs::JobStore,
    peers::LocalRoles,
    workload::{self, Workload},
};
use silicium_embedding::vectors::VectorBlock;
use silicium_node_core::taskbook::{PayloadRef, ResultState};
use std::{collections::BTreeMap, path::PathBuf, time::Duration};
use tokio::sync::mpsc;

const WORDS: &[&str] = &[
    "contrat",
    "résilier",
    "chat",
    "chien",
    "voiture",
    "train",
    "paris",
    "prix",
];

/// A text file of `pages` paragraphs, each long enough to be a passage.
fn document(passages: usize) -> String {
    (0..passages)
        .map(|n| {
            (0..200)
                .map(|w| WORDS[(n * 7 + w * 3) % WORDS.len()])
                .collect::<Vec<_>>()
                .join(" ")
        })
        .collect::<Vec<_>>()
        .join(" ")
}

struct Node {
    context: NodeContext,
    root: PathBuf,
    _commands: mpsc::Receiver<crate::content::ContentCommand>,
}

/// A node whose work and data directories are fresh temporary folders.
fn node(name: &str) -> Node {
    let root =
        std::env::temp_dir().join(format!("silicium-embedding-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(&root).unwrap();
    let key = libp2p::identity::Keypair::generate_ed25519();
    let taskbook = crate::storage::load_taskbook_state(&root.join("data"), &key).unwrap();
    let (tx_content, commands) = mpsc::channel(64);
    let (tx_events, _) = mpsc::channel(64);
    let context = NodeContext {
        local_peer_id: key.public().to_peer_id(),
        hardware: crate::config::read_hardware_bucket(),
        dispatcher_seed: 1,
        taskbook,
        tx_events,
        compute_timeout_s: 60,
        known_tasks: Default::default(),
        content: ContentStore::new(root.join("work"), tx_content),
        connected_workers: Default::default(),
        compute_slots: std::sync::Arc::new(tokio::sync::Semaphore::new(1)),
        roles: LocalRoles::parse("compute,verify"),
        active_tasks: Default::default(),
        activity: ActivityLog::at(None),
        data_dir: root.join("data"),
    };
    Node {
        context,
        root,
        _commands: commands,
    }
}

/// The submitted task of a document search on `TEST_TINY`.
fn submitted(scene_sha256: &str) -> NetworkTask {
    NetworkTask {
        task_id: format!("{}.docs", "a".repeat(32)),
        root_job_id: Some("site-docs".into()),
        scene_path: ContentStore::relative_path(scene_sha256),
        output_path: String::new(),
        seed: "1".into(),
        hardware_hint: None,
        runtime_hint: None,
        runtime_args: Vec::new(),
        runtime_env: BTreeMap::new(),
        runtime_workdir: None,
        runtime_module_path: None,
        runtime_image: None,
        scene_sha256: Some(scene_sha256.into()),
        region: None,
        workload: Some(TEST_TINY.id.into()),
        byte_range: None,
        requested_fragment_count: Some(3),
    }
}

/// Prepares `text` as the publisher does and splits it into 3 fragments.
async fn published_job(node: &Node, text: &str) -> (JobManifest, Vec<NetworkTask>) {
    let file = node.root.join("submitted.txt");
    std::fs::write(&file, text).unwrap();
    let corpus_bytes = TEST_TINY.prepare_input(&file).unwrap().unwrap();
    let sha256 = node.context.content.add_bytes(&corpus_bytes).await.unwrap();
    let task = submitted(&sha256);
    let input = node.context.content.absolute(&task.scene_path);
    TEST_TINY
        .split(&task, &input, &JobSettings::default())
        .unwrap()
}

async fn model_ready(node: &Node) {
    let readiness =
        runtime::wait_for(&TEST_TINY, &node.context.data_dir, Duration::from_secs(30)).await;
    assert!(readiness.is_ready());
    assert!(TEST_TINY.ensure_ready(&node.context).await);
}

/// Computes `task` and returns the published result.
async fn computed(node: &Node, task: &NetworkTask) -> (Vec<u8>, ResultState) {
    TEST_TINY
        .execute(&node.context, task)
        .await
        .expect("computed");
    let bytes = std::fs::read(node.context.content.absolute(&task.output_path)).unwrap();
    (bytes.clone(), result_of(node, &bytes).await)
}

async fn result_of(node: &Node, bytes: &[u8]) -> ResultState {
    let sha256 = node.context.content.add_bytes(bytes).await.unwrap();
    ResultState {
        event_hash: "e".repeat(64),
        result: PayloadRef {
            uri: format!("{}{sha256}", crate::results::CONTENT_SCHEME),
            sha256,
        },
        milestones: Vec::new(),
        approvals: Vec::new(),
        rejections: Vec::new(),
    }
}

#[test]
fn submitted_documents_become_a_corpus_or_a_message() {
    let node = node("prepare");
    let file = node.root.join("notes.txt");
    std::fs::write(&file, "un contrat à résilier").unwrap();
    let corpus_bytes = MULTILINGUAL_E5_SMALL.prepare_input(&file).unwrap().unwrap();
    assert!(corpus_bytes.starts_with(b"{\"format\":\"silicium-corpus/2\""));
    let slides = node.root.join("slides.pptx");
    std::fs::write(&slides, b"PK\x03\x04").unwrap();
    let message = MULTILINGUAL_E5_SMALL.prepare_input(&slides).unwrap_err();
    assert!(
        message.contains("Aucun document pris en charge"),
        "{message}"
    );
}

#[test]
fn workloads_are_registered_and_name_their_model() {
    let workload = workload::find("ai/embedding/multilingual-e5-small").unwrap();
    assert_eq!(workload.storage_dir(), "embedding");
    assert_eq!(
        workload.published_outputs().last().unwrap().target,
        "index/index.json"
    );
    assert_eq!(find(TEST_TINY.id).unwrap().model.id, "test-tiny");
    assert!(find("raytracer").is_none());
}

#[tokio::test]
async fn a_job_is_split_into_fragments_of_whole_passages() {
    let node = node("split");
    let (manifest, tasks) = published_job(&node, &document(7)).await;
    assert_eq!(tasks.len(), 3);
    assert_eq!(manifest.workload, TEST_TINY.id);
    let mut next = 0;
    for (fragment, task) in manifest.fragments.iter().zip(&tasks) {
        let items = fragment.items.unwrap();
        assert_eq!(items.first, next);
        next += items.count;
        assert_eq!(task.byte_range, fragment.byte_range);
        assert_eq!(task.workload.as_deref(), Some(TEST_TINY.id));
        assert!(task.output_path.ends_with("output.bin"));
    }
    assert!(next >= 7, "every passage is in a fragment");
}

#[tokio::test]
async fn honest_vectors_are_accepted_and_approved() {
    let node = node("honest");
    model_ready(&node).await;
    let (manifest, tasks) = published_job(&node, &document(7)).await;
    let (bytes, result) = computed(&node, &tasks[1]).await;
    let fragment = &manifest.fragments[1];
    assert!(TEST_TINY.accepts_result(Some(fragment), &bytes, &[]));
    assert!(
        !TEST_TINY.accepts_result(Some(&manifest.fragments[0]), &bytes, &[]),
        "other passages"
    );
    assert!(!TEST_TINY.accepts_result(None, &bytes, &[]));
    for seed in ["acceptance-1", "acceptance-2"] {
        assert_eq!(
            TEST_TINY
                .verify(&node.context, &tasks[1], &result, seed)
                .await,
            Some(true)
        );
    }
}

#[tokio::test]
async fn faked_vectors_are_rejected() {
    let node = node("faked");
    model_ready(&node).await;
    let (_, tasks) = published_job(&node, &document(7)).await;
    let (bytes, _) = computed(&node, &tasks[0]).await;
    let block = VectorBlock::parse(&bytes).unwrap();
    let dimension = block.dimension;
    // Every vector replaced by another unit vector: right shape, wrong work.
    let fake: Vec<Vec<f32>> = (0..block.count())
        .map(|i| {
            let mut vector = vec![0.0; dimension];
            vector[i % dimension] = 1.0;
            vector
        })
        .collect();
    let faked = VectorBlock::new(dimension, block.first_id, &fake)
        .unwrap()
        .to_bytes();
    let result = result_of(&node, &faked).await;
    assert_eq!(
        TEST_TINY
            .verify(&node.context, &tasks[0], &result, "seed")
            .await,
        Some(false)
    );
    // Vectors of the wrong passages.
    let shifted = VectorBlock {
        first_id: block.first_id + 1,
        ..block
    }
    .to_bytes();
    let result = result_of(&node, &shifted).await;
    assert_eq!(
        TEST_TINY
            .verify(&node.context, &tasks[0], &result, "seed")
            .await,
        Some(false)
    );
}

#[tokio::test]
async fn the_job_store_assembles_an_index_that_can_be_searched() {
    let node = node("assemble");
    model_ready(&node).await;
    let text = format!("{} contrat résilier contrat", document(5));
    let (manifest, tasks) = published_job(&node, &text).await;
    let jobs = JobStore::open(node.context.content.absolute(""));
    jobs.add(manifest.clone()).unwrap();
    for task in &tasks {
        let (bytes, _) = computed(&node, task).await;
        let path = jobs
            .root()
            .join(JobStore::fragment_result_path(&manifest, &task.task_id));
        crate::jobs::store::write_atomic(&path, &bytes).unwrap();
    }
    let first = jobs.assemble(&manifest.job_id).unwrap().unwrap();
    assert!(first.to_string_lossy().ends_with(".passages.jsonl"));
    assert!(jobs.is_assembled(&manifest.job_id));

    let request = search::SearchRequest {
        jobs: vec!["site-docs".into()],
        query: "contrat".into(),
        top_k: 3,
    };
    let response = search::search(&jobs, &node.context.data_dir, request)
        .await
        .unwrap();
    assert_eq!(response.model, "test-tiny");
    assert_eq!(response.hits.len(), 3);
    assert!(
        response
            .hits
            .iter()
            .all(|hit| hit.job_id == "site-docs" && hit.document == "submitted.txt")
    );
    assert!(
        response
            .hits
            .windows(2)
            .all(|pair| pair[0].score >= pair[1].score)
    );

    let partly = search::SearchRequest {
        jobs: vec!["site-docs".into(), "gone".into()],
        query: "contrat".into(),
        top_k: 3,
    };
    let response = search::search(&jobs, &node.context.data_dir, partly)
        .await
        .unwrap();
    assert_eq!(response.unavailable_jobs, vec!["gone".to_string()]);
    assert_eq!(response.hits.len(), 3, "the other jobs are still searched");
    let unknown = search::SearchRequest {
        jobs: vec!["nope".into()],
        query: "x".into(),
        top_k: 3,
    };
    assert!(matches!(
        search::search(&jobs, &node.context.data_dir, unknown).await,
        Err(search::SearchError::NotFound(_))
    ));
    let empty = search::SearchRequest {
        jobs: vec!["site-docs".into()],
        query: " ".into(),
        top_k: 3,
    };
    assert!(matches!(
        search::search(&jobs, &node.context.data_dir, empty).await,
        Err(search::SearchError::Invalid(_))
    ));
}
