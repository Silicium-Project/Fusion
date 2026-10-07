//! Search over assembled indexes, for the BackEnd
//! (`POST /v1/embedding/search`, control token required).
//!
//! The BackEnd sends the jobs of one collection (the jobs a person filled
//! with documents, all of the same model) and the query; the publisher
//! embeds the query with the same pinned model, searches every index and
//! returns the best passages. Indexes are read from the job results
//! (`results/<job>.index.json`, `.vectors.f32`, `.passages.jsonl`) and kept
//! in memory up to `SILICIUM_EMBEDDING_INDEX_CACHE_MB` (default 512),
//! least recently used first out.

use super::{Embedding, runtime};
use crate::jobs::{JobStore, result_file};
use serde::{Deserialize, Serialize};
use silicium_embedding::index::{Index, IndexFiles, top_k};
use std::{
    collections::HashMap,
    path::Path,
    sync::{Arc, LazyLock, Mutex},
    time::Duration,
};

/// Most jobs searched at once.
pub(crate) const MAX_JOBS: usize = 200;
/// Most results returned.
pub(crate) const MAX_TOP_K: usize = 50;
/// Longest query, in characters.
pub(crate) const MAX_QUERY_CHARS: usize = 1_000;
/// How long a query waits for the model on its first use.
const MODEL_WAIT: Duration = Duration::from_secs(5);

/// A search request.
#[derive(Debug, Clone, Deserialize)]
pub(crate) struct SearchRequest {
    /// Job identifiers as the BackEnd knows them (root job ids).
    pub(crate) jobs: Vec<String>,
    pub(crate) query: String,
    #[serde(default = "default_top_k")]
    pub(crate) top_k: usize,
}

fn default_top_k() -> usize {
    10
}

/// One result.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub(crate) struct SearchHit {
    pub(crate) job_id: String,
    pub(crate) passage_id: u64,
    pub(crate) document: String,
    pub(crate) page: Option<u32>,
    pub(crate) text: String,
    pub(crate) score: f32,
}

/// The answer.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub(crate) struct SearchResponse {
    pub(crate) model: String,
    pub(crate) hits: Vec<SearchHit>,
    /// Jobs of the request that could not be searched here (unknown, not
    /// finished or unreadable); the others were.
    pub(crate) unavailable_jobs: Vec<String>,
}

/// Why a search could not be answered.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum SearchError {
    /// Malformed request (400).
    Invalid(String),
    /// No job of the request can be searched here (404).
    NotFound(String),
    /// The model is being prepared: try again shortly (503).
    Preparing,
    /// Anything else (500).
    Failed(String),
}

impl axum::response::IntoResponse for SearchError {
    fn into_response(self) -> axum::response::Response {
        use axum::http::{HeaderValue, StatusCode, header};
        let (status, message) = match self {
            SearchError::Invalid(message) => (StatusCode::BAD_REQUEST, message),
            SearchError::NotFound(message) => (StatusCode::NOT_FOUND, message),
            SearchError::Preparing => (StatusCode::SERVICE_UNAVAILABLE, "model_preparing".into()),
            SearchError::Failed(message) => {
                println!(" Search failed: {message}");
                (StatusCode::INTERNAL_SERVER_ERROR, "search_failed".into())
            }
        };
        let mut response =
            (status, axum::Json(serde_json::json!({"error": message}))).into_response();
        if status == StatusCode::SERVICE_UNAVAILABLE {
            response
                .headers_mut()
                .insert(header::RETRY_AFTER, HeaderValue::from_static("10"));
        }
        response
    }
}

/// Answers `request` over the jobs of `jobs`.
pub(crate) async fn search(
    jobs: &JobStore,
    data_dir: &Path,
    request: SearchRequest,
) -> Result<SearchResponse, SearchError> {
    let query = request.query.trim().to_string();
    if query.is_empty() || query.chars().count() > MAX_QUERY_CHARS {
        return Err(SearchError::Invalid(format!(
            "query must be 1 to {MAX_QUERY_CHARS} characters"
        )));
    }
    if request.jobs.is_empty() || request.jobs.len() > MAX_JOBS {
        return Err(SearchError::Invalid(format!(
            "jobs must list 1 to {MAX_JOBS} jobs"
        )));
    }
    let limit = request.top_k.clamp(1, MAX_TOP_K);
    let (workload, indexes, unavailable_jobs) = {
        let jobs = jobs.clone();
        let roots = request.jobs.clone();
        // Reading an index is blocking file I/O: off the async runtime.
        tokio::task::spawn_blocking(move || load_indexes(&jobs, &roots))
            .await
            .map_err(|err| SearchError::Failed(err.to_string()))??
    };
    let encoder = match runtime::wait_for(workload, data_dir, MODEL_WAIT).await {
        runtime::Readiness::Ready(encoder) => encoder,
        runtime::Readiness::Preparing => return Err(SearchError::Preparing),
        runtime::Readiness::Unavailable(error) => return Err(SearchError::Failed(error)),
    };
    tokio::task::spawn_blocking(move || {
        let vector = encoder
            .embed_query(&query)
            .map_err(|err| SearchError::Failed(err.to_string()))?;
        rank(&indexes, &vector, limit).map(|hits| SearchResponse {
            model: workload.model.id.to_string(),
            hits,
            unavailable_jobs,
        })
    })
    .await
    .map_err(|err| SearchError::Failed(err.to_string()))?
}

/// The best `top_k` passages of all `indexes` (root job id, index).
fn rank(
    indexes: &[(String, Arc<Index>)],
    query: &[f32],
    limit: usize,
) -> Result<Vec<SearchHit>, SearchError> {
    let mut candidates = Vec::new();
    for (position, (_, index)) in indexes.iter().enumerate() {
        let hits = index
            .search(query, limit)
            .map_err(|err| SearchError::Failed(err.to_string()))?;
        candidates.extend(hits.into_iter().map(|hit| ((position, hit.id), hit.score)));
    }
    top_k(candidates.into_iter(), limit)
        .into_iter()
        .map(|((position, id), score)| {
            let (job_id, index) = &indexes[position];
            let passage = index
                .passage(id)
                .map_err(|err| SearchError::Failed(err.to_string()))?;
            Ok(SearchHit {
                job_id: job_id.clone(),
                passage_id: id,
                document: passage.document,
                page: passage.page,
                text: passage.text,
                score,
            })
        })
        .collect()
}

/// Loaded indexes of a search, with the root job id each belongs to.
type JobIndexes = Vec<(String, Arc<Index>)>;

/// The indexes of the jobs that can be searched (all of one document-search
/// workload), and the jobs that cannot (unknown here, not finished, or
/// unreadable). Fails only when no job can be searched.
fn load_indexes(
    jobs: &JobStore,
    root_ids: &[String],
) -> Result<(&'static Embedding, JobIndexes, Vec<String>), SearchError> {
    let mut workload: Option<&'static Embedding> = None;
    let mut indexes = Vec::with_capacity(root_ids.len());
    let mut unavailable = Vec::new();
    for root_id in root_ids {
        let Some(job) = jobs
            .manifest_for_root(root_id)
            .filter(|job| jobs.is_assembled(&job.job_id))
        else {
            unavailable.push(root_id.clone());
            continue;
        };
        let Some(job_workload) = super::find(&job.workload) else {
            unavailable.push(root_id.clone());
            continue;
        };
        if workload.is_some_and(|w| w.id != job_workload.id) {
            return Err(SearchError::Invalid("jobs of different models".into()));
        }
        match cached_index(jobs, &job.job_id) {
            Ok(index) => {
                workload = Some(job_workload);
                indexes.push((root_id.clone(), index));
            }
            Err(err) => {
                println!(" Index of {root_id} unreadable: {err:?}");
                unavailable.push(root_id.clone());
            }
        }
    }
    match workload {
        Some(workload) => Ok((workload, indexes, unavailable)),
        None => Err(SearchError::NotFound(
            "no finished document search among the jobs".into(),
        )),
    }
}

/// Loaded indexes, by job id, with their last use.
struct IndexCache {
    entries: HashMap<String, (Arc<Index>, u64)>,
    clock: u64,
}

static CACHE: LazyLock<Mutex<IndexCache>> = LazyLock::new(|| {
    Mutex::new(IndexCache {
        entries: HashMap::new(),
        clock: 0,
    })
});

/// The index of `job_id`, from the cache or the job's result files. The
/// files are read without holding the cache lock, so that a large index
/// being read does not hold up the searches of other collections.
fn cached_index(jobs: &JobStore, job_id: &str) -> Result<Arc<Index>, SearchError> {
    let poisoned = |_| SearchError::Failed("index cache poisoned".into());
    {
        let mut cache = CACHE.lock().map_err(poisoned)?;
        cache.clock += 1;
        let now = cache.clock;
        if let Some((index, used)) = cache.entries.get_mut(job_id) {
            *used = now;
            return Ok(index.clone());
        }
    }
    let read = |extension: &str| {
        std::fs::read(jobs.root().join(result_file(job_id, extension)))
            .map_err(|err| SearchError::Failed(err.to_string()))
    };
    let files = IndexFiles {
        manifest: read("index.json")?,
        vectors: read("vectors.f32")?,
        passages: read("passages.jsonl")?,
    };
    let index =
        Arc::new(Index::from_files(files).map_err(|err| SearchError::Failed(err.to_string()))?);
    let mut cache = CACHE.lock().map_err(poisoned)?;
    cache.clock += 1;
    let now = cache.clock;
    cache
        .entries
        .insert(job_id.to_string(), (index.clone(), now));
    evict(&mut cache, cache_budget());
    Ok(index)
}

/// Drops the least recently used indexes until the cache fits `budget`
/// bytes (the most recent one is always kept).
fn evict(cache: &mut IndexCache, budget: usize) {
    loop {
        let total: usize = cache
            .entries
            .values()
            .map(|(index, _)| index.memory_bytes())
            .sum();
        if total <= budget || cache.entries.len() <= 1 {
            return;
        }
        let oldest = cache
            .entries
            .iter()
            .min_by_key(|(_, (_, used))| *used)
            .map(|(id, _)| id.clone());
        if let Some(id) = oldest {
            cache.entries.remove(&id);
        }
    }
}

fn cache_budget() -> usize {
    std::env::var("SILICIUM_EMBEDDING_INDEX_CACHE_MB")
        .ok()
        .and_then(|value| value.trim().parse::<usize>().ok())
        .unwrap_or(512)
        .saturating_mul(1024 * 1024)
}
