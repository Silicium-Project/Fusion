//! Canaries ("exercices corrigés"): public examples of the model (the Hub's
//! widget examples, converted by the BackEnd into items: `canaries` of the
//! request) that the publisher mixes with the user's items, at random
//! places, so that a worker cannot tell them apart. Only the publisher knows
//! where they are: the plan stays in its data directory
//! (`<data>/ai/hf/canaries/plans/<batch sha256>.json`), never in the shared
//! batch.
//!
//! - **Learning**: the answer to a canary becomes its reference once an
//!   independent verifier ran that very item again and approved the
//!   fragment (the verifier's sample is drawn from its acceptance, so the
//!   publisher knows which items it ran). A reference is per model,
//!   parameters and input (`<data>/ai/hf/canaries/references/<hash>.json`).
//! - **Checking**: when a worker publishes a fragment holding a canary with
//!   a reference, the publisher compares the answer with the task's metric
//!   ([`super::compare`]) before any verifier; a wrong answer is rejected
//!   (the publisher records itself as verifier with a negative verdict): the
//!   attempt fails, another worker computes the fragment, and the failed
//!   attempt lowers the worker's reputation in the task book.
//! - **Assembly**: the canaries' answers are removed and the user's items
//!   numbered again from 0.
//!
//! Limits: the examples are public, so a worker that knows them could
//! answer them right and cheat on the rest; they add checks to the
//! verifiers' samples, they do not replace them.

use super::{batch::Answer, compare};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::hash_map::RandomState,
    hash::{BuildHasher, Hasher},
    path::{Path, PathBuf},
    sync::OnceLock,
};

const PLAN_FORMAT: &str = "silicium-hf-canaries/1";
/// One canary for this many user items (at least one per job).
const ITEMS_PER_CANARY: usize = 32;
/// Canaries in one job, at most.
const MAX_CANARIES: usize = 16;

static ROOT: OnceLock<PathBuf> = OnceLock::new();

/// Enables canaries, kept under `<data dir>/ai/hf/canaries` (called once at
/// start; without it, requests are built without canaries).
pub(crate) fn init(data_dir: &Path) {
    let _ = ROOT.set(data_dir.join("ai").join("hf").join("canaries"));
}

fn root() -> Option<&'static PathBuf> {
    ROOT.get()
}

/// Where the canaries of a batch are.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub(crate) struct Plan {
    pub(crate) format: String,
    pub(crate) task: String,
    pub(crate) key: String,
    pub(crate) canaries: Vec<Placed>,
}

/// One canary of a batch: its item id and the key of its reference.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct Placed {
    pub(crate) id: u64,
    pub(crate) reference: String,
}

/// The key of the reference of a canary: model, parameters and input.
pub(crate) fn reference_key(
    model_key: &str,
    parameters: &Map<String, Value>,
    inputs: &Value,
) -> String {
    let mut hasher = Sha256::new();
    hasher.update(model_key.as_bytes());
    hasher.update(b"\n");
    hasher.update(serde_json::to_vec(parameters).unwrap_or_default());
    hasher.update(b"\n");
    hasher.update(serde_json::to_vec(inputs).unwrap_or_default());
    hasher
        .finalize()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// A random number (the hasher of a fresh `RandomState` is seeded by the
/// operating system).
fn random() -> u64 {
    let mut hasher = RandomState::new().build_hasher();
    hasher.write_u64(0);
    hasher.finish()
}

/// Mixes `canaries` into `items` (see the module documentation) and returns
/// every item and the plan's canaries. No canary when `canaries` is empty or
/// canaries are not enabled on this node.
pub(crate) fn mix(
    items: Vec<Value>,
    canaries: &[Value],
    model_key: &str,
    parameters: &Map<String, Value>,
) -> (Vec<Value>, Vec<Placed>) {
    mix_with(
        items,
        canaries,
        model_key,
        parameters,
        root().is_some(),
        random,
    )
}

fn mix_with(
    items: Vec<Value>,
    canaries: &[Value],
    model_key: &str,
    parameters: &Map<String, Value>,
    enabled: bool,
    mut random: impl FnMut() -> u64,
) -> (Vec<Value>, Vec<Placed>) {
    let usable: Vec<&Value> = canaries.iter().filter(|c| !c.is_null()).collect();
    if !enabled || usable.is_empty() || items.is_empty() {
        return (items, Vec::new());
    }
    let count = (items.len() / ITEMS_PER_CANARY).clamp(1, MAX_CANARIES);
    // `None`: a user item, in order; `Some(n)`: the n-th canary.
    let mut order: Vec<Option<usize>> = vec![None; items.len()];
    for n in 0..count {
        let position = (random() % (order.len() as u64 + 1)) as usize;
        order.insert(position, Some(n));
    }
    let mut users = items.into_iter();
    let mut mixed = Vec::with_capacity(order.len());
    let mut placed = Vec::with_capacity(count);
    for (id, slot) in order.into_iter().enumerate() {
        match slot {
            None => mixed.push(users.next().unwrap_or(Value::Null)),
            Some(n) => {
                let inputs = usable[n % usable.len()].clone();
                placed.push(Placed {
                    id: id as u64,
                    reference: reference_key(model_key, parameters, &inputs),
                });
                mixed.push(inputs);
            }
        }
    }
    (mixed, placed)
}

fn plan_path(batch_sha256: &str) -> Option<PathBuf> {
    let valid = batch_sha256.len() == 64 && batch_sha256.bytes().all(|b| b.is_ascii_hexdigit());
    valid.then(|| root().map(|root| root.join("plans").join(format!("{batch_sha256}.json"))))?
}

fn reference_path(reference: &str) -> Option<PathBuf> {
    let valid = reference.len() == 64 && reference.bytes().all(|b| b.is_ascii_hexdigit());
    valid.then(|| root().map(|root| root.join("references").join(format!("{reference}.json"))))?
}

fn write(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|err| err.to_string())?;
    }
    crate::jobs::store::write_atomic(path, bytes)
}

/// Keeps the plan of the batch whose SHA-256 is `batch_sha256`.
pub(crate) fn save_plan(batch_sha256: &str, plan: &Plan) -> Result<(), String> {
    let path = plan_path(batch_sha256).ok_or("canaries not enabled")?;
    write(
        &path,
        &serde_json::to_vec(plan).map_err(|err| err.to_string())?,
    )
}

/// The plan of a batch, when it has canaries.
pub(crate) fn plan_of(batch_sha256: &str) -> Option<Plan> {
    let bytes = std::fs::read(plan_path(batch_sha256)?).ok()?;
    serde_json::from_slice::<Plan>(&bytes)
        .ok()
        .filter(|plan| plan.format == PLAN_FORMAT)
}

/// A new plan.
pub(crate) fn new_plan(task: &str, key: &str, canaries: Vec<Placed>) -> Plan {
    Plan {
        format: PLAN_FORMAT.into(),
        task: task.into(),
        key: key.into(),
        canaries,
    }
}

/// The learned answer to a canary.
fn reference(reference: &str) -> Option<Value> {
    let bytes = std::fs::read(reference_path(reference)?).ok()?;
    serde_json::from_slice(&bytes).ok()
}

/// Why the answers of a fragment (`answers`, ids from its first item) fail
/// a canary with a reference; `None` when none fails.
pub(crate) fn wrong_canary(plan: &Plan, answers: &[Answer]) -> Option<String> {
    let metric = compare::metric(&plan.task)?;
    for canary in &plan.canaries {
        let Some(answer) = answers.iter().find(|a| a.id == canary.id) else {
            continue;
        };
        let Some(expected) = reference(&canary.reference) else {
            continue;
        };
        let score = metric.similarity(&answer.output, &expected);
        if !metric.accept(&[score]) {
            return Some(format!(
                "item {} is a known example answered wrongly ({score:.2})",
                canary.id
            ));
        }
    }
    None
}

/// Keeps as references the answers to the canaries an independent verifier
/// ran again (`checked`: ids it ran) and approved; an existing reference is
/// kept.
pub(crate) fn learn(plan: &Plan, answers: &[Answer], checked: &[u64]) {
    for canary in &plan.canaries {
        if !checked.contains(&canary.id) {
            continue;
        }
        let Some(answer) = answers.iter().find(|a| a.id == canary.id) else {
            continue;
        };
        let Some(path) = reference_path(&canary.reference) else {
            continue;
        };
        if path.exists() {
            continue;
        }
        if let Ok(bytes) = serde_json::to_vec(&answer.output)
            && write(&path, &bytes).is_ok()
        {
            println!(" Canary reference learned for model {}", plan.key);
        }
    }
}

/// The answers without the canaries, numbered again from 0.
pub(crate) fn strip(plan: &Plan, answers: Vec<Answer>) -> Vec<Answer> {
    answers
        .into_iter()
        .filter(|answer| !plan.canaries.iter().any(|c| c.id == answer.id))
        .enumerate()
        .map(|(id, answer)| Answer {
            id: id as u64,
            output: answer.output,
        })
        .collect()
}

/// Ids of `items` (a fragment, in order) at the sample indices `picks`.
pub(crate) fn ids_at(first: u64, picks: &[usize]) -> Vec<u64> {
    picks.iter().map(|&index| first + index as u64).collect()
}

#[cfg(test)]
pub(crate) fn set_root_for_tests(root: PathBuf) {
    let _ = ROOT.set(root);
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn counter() -> impl FnMut() -> u64 {
        let mut state = 7u64;
        move || {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            state >> 11
        }
    }

    #[test]
    fn canaries_are_mixed_in_and_removed_again() {
        let users: Vec<Value> = (0..70).map(|n| json!(format!("user {n}"))).collect();
        let parameters = Map::new();
        let (mixed, placed) = mix_with(
            users.clone(),
            &[json!("I like you")],
            "m",
            &parameters,
            true,
            counter(),
        );
        assert_eq!(placed.len(), 2, "one per 32 items");
        assert_eq!(mixed.len(), 72);
        for canary in &placed {
            assert_eq!(mixed[canary.id as usize], json!("I like you"));
        }
        let plan = new_plan("text-classification", "m", placed);
        let answers: Vec<Answer> = mixed
            .iter()
            .enumerate()
            .map(|(id, inputs)| Answer {
                id: id as u64,
                output: inputs.clone(),
            })
            .collect();
        let stripped = strip(&plan, answers);
        let outputs: Vec<Value> = stripped.iter().map(|a| a.output.clone()).collect();
        assert_eq!(outputs, users, "user answers back in order");
        assert!(stripped.iter().enumerate().all(|(n, a)| a.id == n as u64));
    }

    #[test]
    fn no_canary_without_examples_or_when_disabled() {
        let users = vec![json!("a")];
        let parameters = Map::new();
        assert!(
            mix_with(users.clone(), &[], "m", &parameters, true, counter())
                .1
                .is_empty()
        );
        assert!(
            mix_with(
                users.clone(),
                &[json!("x")],
                "m",
                &parameters,
                false,
                counter()
            )
            .1
            .is_empty()
        );
        let (mixed, placed) = mix_with(users, &[json!("x")], "m", &parameters, true, counter());
        assert_eq!((mixed.len(), placed.len()), (2, 1), "at least one per job");
    }

    #[test]
    fn a_reference_depends_on_model_parameters_and_input() {
        let mut parameters = Map::new();
        let base = reference_key("m", &parameters, &json!("x"));
        assert_ne!(base, reference_key("n", &parameters, &json!("x")));
        assert_ne!(base, reference_key("m", &parameters, &json!("y")));
        parameters.insert("top_k".into(), json!(3));
        assert_ne!(base, reference_key("m", &parameters, &json!("x")));
    }

    #[test]
    fn a_learned_reference_catches_a_wrong_answer() {
        let root = std::env::temp_dir().join(format!("silicium-canaries-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        set_root_for_tests(root);
        let reference = reference_key("m", &Map::new(), &json!("I like you"));
        let plan = new_plan(
            "text-classification",
            "m",
            vec![Placed {
                id: 5,
                reference: reference.clone(),
            }],
        );
        let label = |label: &str| {
            vec![Answer {
                id: 5,
                output: json!([{"label": label, "score": 0.9}]),
            }]
        };
        // Nothing learned yet: nothing to check.
        assert_eq!(wrong_canary(&plan, &label("NEGATIVE")), None);
        // Not run again by the verifier: not learned.
        learn(&plan, &label("POSITIVE"), &[4]);
        assert_eq!(wrong_canary(&plan, &label("NEGATIVE")), None);
        learn(&plan, &label("POSITIVE"), &[5]);
        assert_eq!(wrong_canary(&plan, &label("POSITIVE")), None);
        assert!(wrong_canary(&plan, &label("NEGATIVE")).is_some());
        // A later answer does not replace the reference.
        learn(&plan, &label("NEGATIVE"), &[5]);
        assert!(wrong_canary(&plan, &label("NEGATIVE")).is_some());
    }
}
