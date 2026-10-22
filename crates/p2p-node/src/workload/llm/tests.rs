//! Batch AI workload, with the test model and the fake Ollama of
//! `silicium-llm`: preparation, split, compute, verification, assembly by
//! the job store, preview of verified fragments.

use super::*;
use crate::{
    activity::ActivityLog,
    content::ContentStore,
    jobs::JobStore,
    peers::LocalRoles,
    workload::{self, Workload},
};
use serde_json::{Value, json};
use silicium_llm::{answers::Answer, testing};
use silicium_node_core::taskbook::{PayloadRef, ResultState};
use std::{
    collections::BTreeMap,
    path::PathBuf,
    sync::{LazyLock, mpsc as std_mpsc},
    time::Duration,
};
use tokio::sync::mpsc;

/// One fake Ollama for the whole test process, on a runtime of its own (a
/// test's runtime ends with the test).
static FAKE: LazyLock<String> = LazyLock::new(|| {
    let (sender, receiver) = std_mpsc::channel();
    std::thread::spawn(move || {
        let runtime = tokio::runtime::Runtime::new().unwrap();
        runtime.block_on(async move {
            let (url, _) = testing::spawn("127.0.0.1:0", testing::Behaviour::Honest)
                .await
                .unwrap();
            sender.send(url).unwrap();
            std::future::pending::<()>().await;
        });
    });
    let url = receiver.recv().unwrap();
    let _ = runtime::TEST_OLLAMA_URL.set(url.clone());
    url
});

struct Node {
    context: NodeContext,
    root: PathBuf,
    _commands: mpsc::Receiver<crate::content::ContentCommand>,
}

fn node(name: &str) -> Node {
    LazyLock::force(&FAKE);
    let root = std::env::temp_dir().join(format!("silicium-llm-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(&root).unwrap();
    let key = libp2p::identity::Keypair::generate_ed25519();
    let taskbook = crate::storage::load_taskbook_state(&root.join("data"), &key).unwrap();
    let (tx_content, commands) = mpsc::channel(64);
    let (tx_events, _) = mpsc::channel(64);
    let (tx_publish, _) = mpsc::channel(64);
    let context = NodeContext {
        local_peer_id: key.public().to_peer_id(),
        hardware: crate::config::read_hardware_bucket(),
        dispatcher_seed: 1,
        taskbook,
        tx_events,
        tx_publish,
        compute_timeout_s: 60,
        job_settings: crate::jobs::JobSettings::default(),
        known_tasks: Default::default(),
        content: ContentStore::new(root.join("work"), tx_content),
        online_workers: Default::default(),
        available_compute_authors: Default::default(),
        compute_slots: std::sync::Arc::new(tokio::sync::Semaphore::new(1)),
        roles: LocalRoles::parse("compute,verify"),
        active_tasks: Default::default(),
        pending_admissions: Default::default(),
        activity: ActivityLog::at(None),
        data_dir: root.join("data"),
    };
    Node {
        context,
        root,
        _commands: commands,
    }
}

fn request(output: Value, count: usize) -> Value {
    json!({
        "format": "silicium-llm-request/1",
        "task": "classify",
        "instruction": "Classe cet avis.",
        "output": output,
        "max_tokens": 64,
        "source": {"name": "avis.csv", "column": "avis"},
        "items": (0..count).map(|n| format!("Avis numéro {n} : livraison {} et produit conforme.", ["rapide", "lente", "correcte"][n % 3])).collect::<Vec<_>>(),
    })
}

fn submitted(sha256: &str) -> NetworkTask {
    NetworkTask {
        task_id: format!("{}.llm", "b".repeat(32)),
        root_job_id: Some("site-llm".into()),
        parent_task_id: None,
        scene_path: ContentStore::relative_path(sha256),
        output_path: String::new(),
        seed: "1".into(),
        hardware_hint: None,
        runtime_hint: None,
        runtime_args: Vec::new(),
        runtime_env: BTreeMap::new(),
        runtime_workdir: None,
        runtime_module_path: None,
        runtime_image: None,
        scene_sha256: Some(sha256.into()),
        region: None,
        workload: Some(TEST_TINY.id.into()),
        solana_payment: None,
        byte_range: None,
        requested_fragment_count: Some(3),
        delegation_depth: 0,
    }
}

async fn published_job(node: &Node, request: &Value) -> (JobManifest, Vec<NetworkTask>) {
    let file = node.root.join("request.json");
    std::fs::write(&file, serde_json::to_vec(request).unwrap()).unwrap();
    let batch_bytes = TEST_TINY.prepare_input(&file).unwrap().unwrap();
    let sha256 = node.context.content.add_bytes(&batch_bytes).await.unwrap();
    let task = submitted(&sha256);
    let input = node.context.content.absolute(&task.scene_path);
    TEST_TINY
        .split(&task, &input, &JobSettings::default())
        .unwrap()
}

async fn model_ready(node: &Node) {
    let client =
        runtime::wait_for(&TEST_TINY, &node.context.data_dir, Duration::from_secs(30)).await;
    assert!(client.is_some(), "the model is imported into Ollama");
    assert!(
        TEST_TINY
            .ensure_ready(&node.context, &submitted(&"0".repeat(64)))
            .await
    );
}

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

fn labels() -> Value {
    json!({"kind": "label", "labels": ["positif", "négatif", "neutre"]})
}

#[test]
fn requests_become_a_batch_or_a_message() {
    let node = node("prepare");
    let file = node.root.join("request.json");
    std::fs::write(&file, serde_json::to_vec(&request(labels(), 2)).unwrap()).unwrap();
    let batch_bytes = QWEN2_5_1_5B_INSTRUCT.prepare_input(&file).unwrap().unwrap();
    assert!(
        batch_bytes.starts_with(
            b"{\"format\":\"silicium-llm-batch/1\",\"model\":\"qwen2.5-1.5b-instruct\""
        )
    );
    let mut bad = request(labels(), 2);
    bad["items"] = json!([]);
    std::fs::write(&file, serde_json::to_vec(&bad).unwrap()).unwrap();
    let message = QWEN2_5_1_5B_INSTRUCT.prepare_input(&file).unwrap_err();
    assert!(message.contains("aucun élément"), "{message}");
    std::fs::write(&file, b"%PDF").unwrap();
    assert!(QWEN2_5_1_5B_INSTRUCT.prepare_input(&file).is_err());
}

#[test]
fn workloads_are_registered_with_a_long_lease() {
    let workload = workload::find("ai/llm/qwen2.5-1.5b-instruct").unwrap();
    assert_eq!(workload.storage_dir(), "llm");
    assert_eq!(
        workload.published_outputs().last().unwrap().target,
        "answers/result.json"
    );
    let terms = workload.terms(TaskTerms::default());
    assert!(terms.lease_ms >= 5 * 60_000);
    assert_eq!(
        terms.verifications_required,
        TaskTerms::default().verifications_required
    );
    assert_eq!(
        workload::find("raytracer")
            .unwrap()
            .terms(TaskTerms::default()),
        TaskTerms::default()
    );
    assert_eq!(find(TEST_TINY.id).unwrap().model.id, "test-tiny");
}

#[tokio::test]
async fn a_job_is_split_into_fragments_of_whole_items() {
    let node = node("split");
    let (manifest, tasks) = published_job(&node, &request(labels(), 10)).await;
    assert_eq!(tasks.len(), 3);
    let counts: Vec<u64> = manifest
        .fragments
        .iter()
        .map(|f| f.items.unwrap().count)
        .collect();
    assert_eq!(counts, [3, 3, 4]);
    assert!(
        tasks
            .iter()
            .all(|task| task.workload.as_deref() == Some(TEST_TINY.id))
    );
}

#[tokio::test]
async fn honest_answers_are_accepted_and_approved() {
    let node = node("honest");
    model_ready(&node).await;
    for output in [
        labels(),
        json!({"kind": "text"}),
        json!({"kind": "fields", "fields": ["livraison"]}),
    ] {
        let (manifest, tasks) = published_job(&node, &request(output, 9)).await;
        let (bytes, result) = computed(&node, &tasks[1]).await;
        assert!(TEST_TINY.accepts_result(Some(&manifest.fragments[1]), &bytes, &[]));
        assert!(
            !TEST_TINY.accepts_result(Some(&manifest.fragments[0]), &bytes, &[]),
            "other items"
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
}

#[tokio::test]
async fn faked_answers_are_rejected() {
    let node = node("faked");
    model_ready(&node).await;
    let (_, tasks) = published_job(&node, &request(json!({"kind": "text"}), 9)).await;
    let (bytes, _) = computed(&node, &tasks[0]).await;
    let honest = silicium_llm::answers::parse(&bytes, 0, 3).unwrap();
    let lie = |output: Value| -> Vec<Answer> {
        honest
            .iter()
            .map(|answer| Answer {
                id: answer.id,
                output: output.clone(),
            })
            .collect()
    };
    for faked in [lie(json!("Lorem ipsum dolor sit amet.")), lie(json!(""))] {
        let result = result_of(&node, &silicium_llm::answers::to_bytes(&faked).unwrap()).await;
        assert_eq!(
            TEST_TINY
                .verify(&node.context, &tasks[0], &result, "seed")
                .await,
            Some(false)
        );
    }
    // Answers of other items, or of the wrong shape.
    let shifted: Vec<Answer> = honest
        .iter()
        .map(|a| Answer {
            id: a.id + 1,
            output: a.output.clone(),
        })
        .collect();
    let result = result_of(&node, &silicium_llm::answers::to_bytes(&shifted).unwrap()).await;
    assert_eq!(
        TEST_TINY
            .verify(&node.context, &tasks[0], &result, "seed")
            .await,
        Some(false)
    );
    let result = result_of(
        &node,
        &silicium_llm::answers::to_bytes(&lie(json!({"x": "y"}))).unwrap(),
    )
    .await;
    assert_eq!(
        TEST_TINY
            .verify(&node.context, &tasks[0], &result, "seed")
            .await,
        Some(false)
    );
}

#[tokio::test]
async fn the_job_store_assembles_the_answers_and_previews_fragments() {
    let node = node("assemble");
    model_ready(&node).await;
    let (manifest, tasks) = published_job(&node, &request(labels(), 7)).await;
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
    assert!(first.to_string_lossy().ends_with(".answers.jsonl"));
    assert!(jobs.is_assembled(&manifest.job_id));
    let answers = std::fs::read_to_string(&first).unwrap();
    assert_eq!(answers.lines().count(), 7);
    let line: Value = serde_json::from_str(answers.lines().nth(4).unwrap()).unwrap();
    assert_eq!(line["id"], 4);
    assert!(line["input"].as_str().unwrap().starts_with("Avis numéro 4"));
    assert!(["positif", "négatif", "neutre"].contains(&line["output"].as_str().unwrap()));

    let input = jobs.root().join(ContentStore::relative_path(
        manifest.scene_sha256.as_deref().unwrap(),
    ));
    let result = std::fs::read(
        jobs.root()
            .join(JobStore::fragment_result_path(&manifest, &tasks[2].task_id)),
    )
    .unwrap();
    let preview = fragment_preview(&input, &manifest.fragments[2], &result).unwrap();
    let preview = String::from_utf8(preview).unwrap();
    assert_eq!(
        preview.lines().count() as u64,
        manifest.fragments[2].items.unwrap().count
    );
    assert!(preview.lines().last().unwrap().contains("\"id\":6"));
    assert!(
        fragment_preview(&input, &manifest.fragments[0], &result).is_none(),
        "other items"
    );
}

#[tokio::test]
async fn a_node_without_ollama_is_never_ready() {
    // The URL is the fake's in tests; a client for a dead server is refused.
    let client = silicium_llm::ollama::Ollama::new("http://127.0.0.1:9").unwrap();
    assert!(client.version().await.is_err());
}
