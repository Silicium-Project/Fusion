//! Hugging Face workload with a fake AI runtime and a fake Hub (one axum
//! server for the process): request, split, model preparation (download,
//! hash check, layout, load), compute, verification, assembly.

use super::{manifest::Manifest, *};
use crate::{activity::ActivityLog, content::ContentStore, peers::LocalRoles, workload};
use axum::{
    Json, Router,
    extract::Path as AxumPath,
    http::StatusCode,
    routing::{get, post},
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use silicium_node_core::taskbook::{PayloadRef, ResultState};
use std::{
    collections::BTreeMap,
    path::PathBuf,
    sync::{LazyLock, mpsc as std_mpsc},
    time::Duration,
};
use tokio::sync::mpsc;

const CONFIG: &[u8] = br#"{"model_type":"tiny"}"#;
const CONFIG_GIT: &str = "2bca4099ca46ea25d5b5df22f3e99f26f1389ec5";
const WEIGHTS: &[u8] = b"SAFETENSORS-TEST";
const REVISION: &str = "1234567890abcdef1234567890abcdef12345678";

/// The fake runtime labels a text with its first word; the fake Hub serves
/// the files of `org/tiny-classifier` (and wrong bytes for `org/broken`).
async fn fake_server() -> String {
    async fn health() -> Json<Value> {
        Json(json!({"format": "silicium-ai-runtime/1", "tasks": ["text-classification"]}))
    }
    async fn load(Json(body): Json<Value>) -> StatusCode {
        let dir = PathBuf::from(body["model_dir"].as_str().unwrap_or(""));
        let config = std::fs::read(dir.join("config.json")).unwrap_or_default();
        let weights = std::fs::read(dir.join("weights/model.safetensors")).unwrap_or_default();
        if config == CONFIG && weights == WEIGHTS {
            StatusCode::OK
        } else {
            StatusCode::UNPROCESSABLE_ENTITY
        }
    }
    async fn run(Json(body): Json<Value>) -> Json<Value> {
        let outputs: Vec<Value> = body["items"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| {
                let text = item["inputs"].as_str().unwrap_or("");
                let label = text.split_whitespace().next().unwrap_or("").to_lowercase();
                json!([{"label": label, "score": 0.9}, {"label": "other", "score": 0.1}])
            })
            .collect();
        Json(json!({"outputs": outputs}))
    }
    async fn file(
        AxumPath((owner, name, _revision, path)): AxumPath<(String, String, String, String)>,
    ) -> Vec<u8> {
        match (owner.as_str(), name.as_str(), path.as_str()) {
            ("org", "tiny-classifier", "config.json") => CONFIG.to_vec(),
            ("org", "tiny-classifier", "weights/model.safetensors") => WEIGHTS.to_vec(),
            ("org", "broken", "config.json") => CONFIG.to_vec(),
            _ => b"not the real one".to_vec(),
        }
    }
    let router = Router::new()
        .route("/v1/health", get(health))
        .route("/v1/load", post(load))
        .route("/v1/run", post(run))
        .route("/{owner}/{name}/resolve/{revision}/{*path}", get(file));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    url
}

static FAKE: LazyLock<String> = LazyLock::new(|| {
    let (sender, receiver) = std_mpsc::channel();
    std::thread::spawn(move || {
        tokio::runtime::Runtime::new()
            .unwrap()
            .block_on(async move {
                sender.send(fake_server().await).unwrap();
                std::future::pending::<()>().await;
            });
    });
    let url = receiver.recv().unwrap();
    let _ = runtime::TEST_URLS.set((url.clone(), url.clone()));
    url
});

fn manifest_for(repository: &str) -> Manifest {
    let weights_sha256 = manifest::hex(&Sha256::digest(WEIGHTS));
    let mut manifest: Manifest = serde_json::from_value(json!({
        "format": "silicium-model/1", "key": "", "digest": "",
        "repository": repository, "revision": REVISION,
        "task": "text-classification", "library": "transformers", "runtime": "python",
        "loader": {"auto_model": "AutoModelForSequenceClassification", "model_type": "tiny"},
        "files": [
            {"path": "config.json", "size": CONFIG.len(), "git_oid": CONFIG_GIT},
            {"path": "weights/model.safetensors", "size": WEIGHTS.len(), "sha256": weights_sha256},
        ],
        "total_bytes": CONFIG.len() + WEIGHTS.len(),
        "hardware_class": "A", "licence": "apache-2.0",
    }))
    .unwrap();
    manifest.seal();
    manifest
}

fn workload_for(manifest: &Manifest) -> &'static Hf {
    find(&format!("ai/hf/{}/{}", manifest.task, manifest.key)).unwrap()
}

struct Node {
    context: NodeContext,
    root: PathBuf,
    _commands: mpsc::Receiver<crate::content::ContentCommand>,
}

fn node(name: &str) -> Node {
    LazyLock::force(&FAKE);
    let root = std::env::temp_dir().join(format!("silicium-hf-{name}-{}", std::process::id()));
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

fn request(manifest: &Manifest, items: &[&str]) -> Value {
    json!({
        "format": "silicium-hf-request/1",
        "task": manifest.task,
        "model": manifest,
        "parameters": {"top_k": 2},
        "items": items,
    })
}

const TEXTS: &[&str] = &[
    "Positif : livraison rapide.",
    "Négatif : colis abîmé.",
    "Neutre : rien à signaler.",
    "Positif : très bon produit.",
    "Négatif : en retard.",
];

fn submitted(sha256: &str, workload: &Hf) -> NetworkTask {
    NetworkTask {
        task_id: format!("{}.hf", "c".repeat(32)),
        root_job_id: Some("site-hf".into()),
        scene_path: ContentStore::relative_path(sha256),
        output_path: String::new(),
        seed: "7".into(),
        hardware_hint: None,
        runtime_hint: None,
        runtime_args: Vec::new(),
        runtime_env: BTreeMap::new(),
        runtime_workdir: None,
        runtime_module_path: None,
        runtime_image: None,
        scene_sha256: Some(sha256.into()),
        region: None,
        workload: Some(workload.id.into()),
        solana_payment: None,
        byte_range: None,
        requested_fragment_count: Some(2),
    }
}

async fn published_job(
    node: &Node,
    workload: &Hf,
    request: &Value,
) -> (JobManifest, Vec<NetworkTask>, PathBuf) {
    let file = node.root.join("request.json");
    std::fs::write(&file, serde_json::to_vec(request).unwrap()).unwrap();
    let batch_bytes = workload.prepare_input(&file).unwrap().unwrap();
    let sha256 = node.context.content.add_bytes(&batch_bytes).await.unwrap();
    let task = submitted(&sha256, workload);
    let input = node.context.content.absolute(&task.scene_path);
    let (job, tasks) = workload
        .split(&task, &input, &JobSettings::default())
        .unwrap();
    (job, tasks, input)
}

async fn wait_ready(node: &Node, workload: &Hf, task: &NetworkTask) -> bool {
    for _ in 0..300 {
        if workload.ensure_ready(&node.context, task).await {
            return true;
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    false
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

#[tokio::test]
async fn a_job_is_split_computed_verified_and_assembled() {
    let node = node("job");
    let manifest = manifest_for("org/tiny-classifier");
    let workload = workload_for(&manifest);
    let (job, tasks, input) = published_job(&node, workload, &request(&manifest, TEXTS)).await;
    assert_eq!(job.workload, workload.id);
    assert_eq!(tasks.len(), 2);
    assert_eq!(
        job.fragments[0].items.unwrap().count + job.fragments[1].items.unwrap().count,
        5
    );

    // The first call starts the preparation; the model is then ready, its
    // files laid out as in the repository, and announced as warm.
    assert!(
        wait_ready(&node, workload, &tasks[0]).await,
        "model prepared"
    );
    let dir = runtime::model_dir(&node.context.data_dir, &manifest.key);
    assert_eq!(
        std::fs::read(dir.join("weights/model.safetensors")).unwrap(),
        WEIGHTS
    );
    assert!(warm_models().contains(&manifest.key));

    let mut results = Vec::new();
    for task in &tasks {
        workload
            .execute(&node.context, task)
            .await
            .expect("computed");
        let bytes = std::fs::read(node.context.content.absolute(&task.output_path)).unwrap();
        let fragment = job
            .fragments
            .iter()
            .find(|f| f.task_id == task.task_id)
            .unwrap();
        assert!(workload.accepts_result(Some(fragment), &bytes, &[]));
        results.push(bytes);
    }
    let first = String::from_utf8(results[0].clone()).unwrap();
    assert!(
        first.starts_with(r#"{"id":0,"output":[{"label":"positif""#),
        "{first}"
    );

    // An honest result is accepted; changed labels or a missing item are not.
    let honest = result_of(&node, &results[0]).await;
    assert_eq!(
        workload
            .verify(&node.context, &tasks[0], &honest, "seed")
            .await,
        Some(true)
    );
    let forged = String::from_utf8(results[0].clone())
        .unwrap()
        .replace("positif", "négatif")
        .replace("neutre", "positif");
    let forged = result_of(&node, forged.as_bytes()).await;
    assert_eq!(
        workload
            .verify(&node.context, &tasks[0], &forged, "seed")
            .await,
        Some(false)
    );
    let truncated = result_of(&node, results[0].split(|b| *b == b'\n').next().unwrap()).await;
    assert_eq!(
        workload
            .verify(&node.context, &tasks[0], &truncated, "seed")
            .await,
        Some(false)
    );

    let outputs = workload.assemble(&job, &input, &results).unwrap();
    let answers = String::from_utf8(outputs[0].bytes.clone()).unwrap();
    assert_eq!(answers.lines().count(), 5);
    let result: Value = serde_json::from_slice(&outputs[1].bytes).unwrap();
    assert_eq!(result["model"]["repository"], "org/tiny-classifier");
    assert_eq!(result["item_count"], 5);
    assert!(workload.assemble(&job, &input, &results[..1]).is_err());
}

#[tokio::test]
async fn a_model_whose_files_do_not_match_is_never_ready() {
    let node = node("broken");
    let manifest = manifest_for("org/broken");
    let workload = workload_for(&manifest);
    let (_, tasks, _) = published_job(&node, workload, &request(&manifest, &TEXTS[..2])).await;
    assert!(!wait_ready(&node, workload, &tasks[0]).await);
    assert!(!warm_models().contains(&manifest.key));
    // The Hub sent another file than the pinned one: reported for quarantine.
    assert!(runtime::model_faults().contains(&manifest.key));
    assert!(
        !runtime::model_dir(&node.context.data_dir, &manifest.key)
            .join("weights")
            .exists()
    );
}

#[test]
fn requests_must_match_the_workload_and_carry_a_sealed_manifest() {
    let node = node("requests");
    let manifest = manifest_for("org/tiny-classifier");
    let workload = workload_for(&manifest);
    let file = node.root.join("request.json");
    let refused = |request: Value| {
        std::fs::write(&file, serde_json::to_vec(&request).unwrap()).unwrap();
        workload.prepare_input(&file).unwrap_err()
    };
    let mut tampered = request(&manifest, TEXTS);
    tampered["model"]["files"][1]["sha256"] = json!("0".repeat(64));
    assert!(refused(tampered).contains("refusé"));
    let mut other_task = request(&manifest, TEXTS);
    other_task["task"] = json!("translation");
    assert!(refused(other_task).contains("ne correspond pas"));
    assert!(refused(request(&manifest, &[])).contains("aucun élément"));
    let mut bad_parameters = request(&manifest, TEXTS);
    bad_parameters["parameters"] = json!([1, 2]);
    assert!(refused(bad_parameters).contains("objet"));
    std::fs::write(&file, b"%PDF").unwrap();
    assert!(workload.prepare_input(&file).is_err());
}

#[test]
fn identifiers_name_a_known_task_and_a_well_formed_key() {
    let manifest = manifest_for("org/tiny-classifier");
    let id = format!("ai/hf/text-classification/{}", manifest.key);
    let a = workload::find(&id).unwrap();
    let b = workload::find(&id).unwrap();
    assert!(std::ptr::eq(a, b), "one workload per identifier");
    assert_eq!(a.storage_dir(), "hf");
    assert!(a.terms(TaskTerms::default()).lease_ms >= 5 * 60_000);
    for bad in [
        "ai/hf/text-to-video/org--model-0123456789ab",
        "ai/hf/text-classification/../../etc",
        "ai/hf/text-classification/Org--Model-0123456789ab",
        "ai/hf/text-classification/short",
        "ai/hf/text-classification",
    ] {
        assert!(workload::find(bad).is_none(), "{bad}");
    }
    assert!(
        workload::find("ai/llm/qwen2.5-1.5b-instruct").is_some(),
        "existing workloads still found"
    );
    assert!(workload::find("raytracer").is_some());
}

#[test]
fn model_files_come_from_the_hub_then_from_peers_by_default() {
    use runtime::{Source, sources};
    assert_eq!(sources(None), vec![Source::Hub, Source::Peers]);
    assert_eq!(
        sources(Some("peers, hub")),
        vec![Source::Peers, Source::Hub]
    );
    assert_eq!(sources(Some("peers,peers")), vec![Source::Peers]);
    assert_eq!(sources(Some("hub")), vec![Source::Hub]);
    assert_eq!(sources(Some("nowhere")), vec![Source::Hub, Source::Peers]);
}

#[tokio::test]
async fn canaries_are_hidden_checked_and_removed() {
    canary::set_root_for_tests(
        std::env::temp_dir().join(format!("silicium-hf-canaries-{}", std::process::id())),
    );
    let node = node("canaries");
    let manifest = manifest_for("org/tiny-classifier");
    let workload = workload_for(&manifest);
    let texts: Vec<&str> = TEXTS.iter().copied().cycle().take(40).collect();
    let mut with_canary = request(&manifest, &texts);
    with_canary["canaries"] = json!(["Canari : exemple public."]);
    let (job, tasks, input) = published_job(&node, workload, &with_canary).await;
    let header = batch::read_header_file(&input).unwrap();
    assert_eq!(header.item_count, 41, "one canary among the items");
    let sha256 = input.file_name().unwrap().to_str().unwrap().to_string();
    let plan = canary::plan_of(&sha256).expect("plan kept by the publisher");
    assert_eq!(plan.canaries.len(), 1);
    assert!(
        wait_ready(&node, workload, &tasks[0]).await,
        "model prepared"
    );

    let mut results = Vec::new();
    for task in &tasks {
        workload
            .execute(&node.context, task)
            .await
            .expect("computed");
        results.push(std::fs::read(node.context.content.absolute(&task.output_path)).unwrap());
    }
    let canary_id = plan.canaries[0].id;
    let (index, fragment) = job
        .fragments
        .iter()
        .enumerate()
        .find(|(_, f)| {
            let items = f.items.unwrap();
            (items.first..items.first + items.count).contains(&canary_id)
        })
        .unwrap();
    let honest = &results[index];
    let forged = String::from_utf8(honest.clone())
        .unwrap()
        .replace(r#""label":"canari""#, r#""label":"positif""#);
    // Nothing learned yet: nothing to reject.
    assert_eq!(workload.audit(fragment, &input, forged.as_bytes()), None);
    // An independent verifier ran the canary again and approved.
    let at = (canary_id - fragment.items.unwrap().first) as usize;
    workload.learn(fragment, &input, honest, &[at]);
    assert_eq!(workload.audit(fragment, &input, honest), None);
    assert!(
        workload
            .audit(fragment, &input, forged.as_bytes())
            .is_some()
    );

    // The user gets its 40 answers, numbered from 0, without the canary.
    let outputs = workload.assemble(&job, &input, &results).unwrap();
    let answers = String::from_utf8(outputs[0].bytes.clone()).unwrap();
    assert_eq!(answers.lines().count(), 40);
    assert!(!answers.contains("canari"));
    assert!(answers.lines().last().unwrap().starts_with(r#"{"id":39,"#));
    let result: Value = serde_json::from_slice(&outputs[1].bytes).unwrap();
    assert_eq!(result["item_count"], 40);
}
