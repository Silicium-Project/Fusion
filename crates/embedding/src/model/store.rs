//! Local cache of model files.
//!
//! Files are kept by hash, as `<root>/<sha256>`, and only ever written
//! complete and checked: a download goes to `<sha256>.partial` while it is
//! hashed, and is renamed once its size and SHA-256 match the
//! [`super::ModelSpec`]; a download stops as soon as it goes past the pinned
//! size. A file already there is checked against its hash, and downloaded
//! again when it does not match (a corrupted disk). A lock file
//! (`<sha256>.lock`) keeps two processes of the machine (the node and the
//! CLI) from downloading the same file at once; the download touches it as
//! it goes, so a lock untouched for [`STALE_LOCK`] belongs to a process that
//! died and is taken over.
//!
//! Files come from `<base url>/<repository>/resolve/<revision>/<name>`: the
//! Hugging Face hub by default, or a mirror with the same layout
//! (`SILICIUM_MODEL_BASE_URL`). The hashes are checked whatever the source.

use super::{ModelFile, ModelSpec};
use crate::{Error, Result};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File},
    io::Write,
    path::{Path, PathBuf},
    time::{Duration, SystemTime},
};

/// Default source of model files.
pub const DEFAULT_BASE_URL: &str = "https://huggingface.co";
/// A download lock untouched for this long is abandoned (crashed process).
pub const STALE_LOCK: Duration = Duration::from_secs(10 * 60);
/// A running download touches its lock every this many bytes.
const LOCK_TOUCH_BYTES: u64 = 8 * 1024 * 1024;

/// Downloads one URL into a sink.
pub trait Fetcher: Send + Sync {
    /// Writes the body of `url` into `sink`.
    fn fetch(&self, url: &str, sink: &mut dyn Write) -> Result<()>;
}

/// [`Fetcher`] over HTTPS.
pub struct HttpFetcher {
    client: reqwest::blocking::Client,
}

impl HttpFetcher {
    pub fn new() -> Result<Self> {
        let client = reqwest::blocking::Client::builder()
            .connect_timeout(Duration::from_secs(20))
            .timeout(Duration::from_secs(60 * 60))
            .user_agent("silicium-embedding")
            .build()
            .map_err(|err| Error::Model(format!("http client: {err}")))?;
        Ok(Self { client })
    }
}

impl Fetcher for HttpFetcher {
    fn fetch(&self, url: &str, sink: &mut dyn Write) -> Result<()> {
        let mut response = self
            .client
            .get(url)
            .send()
            .and_then(|response| response.error_for_status())
            .map_err(|err| Error::Model(format!("download {url}: {err}")))?;
        response
            .copy_to(sink)
            .map_err(|err| Error::Model(format!("download {url}: {err}")))?;
        Ok(())
    }
}

/// Paths of a model's files, once present.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelPaths {
    pub weights: PathBuf,
    pub tokenizer: PathBuf,
}

/// The model files of this machine.
pub struct ModelStore {
    root: PathBuf,
    base_url: String,
    fetcher: Box<dyn Fetcher>,
}

impl ModelStore {
    pub fn new(root: PathBuf, base_url: &str, fetcher: Box<dyn Fetcher>) -> Self {
        Self {
            root,
            base_url: base_url.trim_end_matches('/').to_string(),
            fetcher,
        }
    }

    /// Store under `SILICIUM_MODEL_DIR`, or `<data_dir>/models`, fetching
    /// from `SILICIUM_MODEL_BASE_URL` or [`DEFAULT_BASE_URL`].
    pub fn from_env(data_dir: &Path) -> Result<Self> {
        let root = env_value("SILICIUM_MODEL_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| data_dir.join("models"));
        let base = env_value("SILICIUM_MODEL_BASE_URL").unwrap_or_else(|| DEFAULT_BASE_URL.into());
        Ok(Self::new(root, &base, Box::new(HttpFetcher::new()?)))
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    /// Where the files of `spec` are (or will be).
    pub fn paths(&self, spec: &ModelSpec) -> ModelPaths {
        ModelPaths {
            weights: self.file_path(&spec.weights),
            tokenizer: self.file_path(&spec.tokenizer),
        }
    }

    /// True when every file of `spec` is present with the right size (the
    /// hashes are checked when the model is loaded).
    pub fn is_ready(&self, spec: &ModelSpec) -> bool {
        spec.files().iter().all(|file| {
            fs::metadata(self.file_path(file)).is_ok_and(|meta| meta.len() == file.size)
        })
    }

    /// Downloads the missing or damaged files of `spec` and returns their
    /// paths.
    pub fn ensure(&self, spec: &ModelSpec) -> Result<ModelPaths> {
        for file in spec.files() {
            self.ensure_file(spec.repository, spec.revision, &file)?;
        }
        Ok(self.paths(spec))
    }

    /// Downloads `file` of `repository` at `revision` unless it is already
    /// here and intact, and returns its path. Any pinned file can be kept
    /// here: the language model of the `ai/llm/…` workload is too.
    pub fn ensure_file(
        &self,
        repository: &str,
        revision: &str,
        file: &ModelFile,
    ) -> Result<PathBuf> {
        fs::create_dir_all(&self.root)?;
        let path = self.file_path(file);
        if path.exists() {
            if verify_file(&path, file).is_ok() {
                return Ok(path);
            }
            fs::remove_file(&path)?;
        }
        self.download(&self.file_url(repository, revision, file), file, &path)?;
        Ok(path)
    }

    /// Where `file` is (or will be).
    pub fn file_path(&self, file: &ModelFile) -> PathBuf {
        self.root.join(file.sha256)
    }

    /// URL of a file of `spec`.
    pub fn url(&self, spec: &ModelSpec, file: &ModelFile) -> String {
        self.file_url(spec.repository, spec.revision, file)
    }

    fn file_url(&self, repository: &str, revision: &str, file: &ModelFile) -> String {
        format!(
            "{}/{}/resolve/{}/{}",
            self.base_url, repository, revision, file.name
        )
    }

    fn download(&self, url: &str, file: &ModelFile, path: &Path) -> Result<()> {
        let lock = DownloadLock::acquire(&path.with_extension("lock"))?;
        let partial = path.with_extension("partial");
        let mut sink = HashingWriter::new(File::create(&partial)?)
            .bounded(file.size)
            .touching(lock.path.clone());
        let fetched = self.fetcher.fetch(url, &mut sink);
        let (written, sha256) = sink.finish()?;
        let checked = fetched.and_then(|()| check(file, written, &sha256));
        if let Err(err) = checked {
            let _ = fs::remove_file(&partial);
            return Err(err);
        }
        fs::rename(&partial, path)?;
        Ok(())
    }
}

/// Checks a file on disk against its pinned size and hash.
pub fn verify_file(path: &Path, file: &ModelFile) -> Result<()> {
    let mut source =
        File::open(path).map_err(|err| Error::Model(format!("{} missing: {err}", file.name)))?;
    let mut sink = HashingWriter::new(std::io::sink()).bounded(file.size);
    if std::io::copy(&mut source, &mut sink).is_err() {
        return Err(Error::Model(format!("{} is larger than pinned", file.name)));
    }
    let (written, sha256) = sink.finish()?;
    check(file, written, &sha256)
}

fn check(file: &ModelFile, size: u64, sha256: &str) -> Result<()> {
    if size != file.size || sha256 != file.sha256 {
        return Err(Error::Model(format!(
            "{}: got {size} bytes with SHA-256 {sha256}, expected {} bytes with {}",
            file.name, file.size, file.sha256
        )));
    }
    Ok(())
}

/// Writes through while hashing; refuses to go past `limit` bytes, and
/// touches `lock` as the bytes come.
struct HashingWriter<W: Write> {
    inner: W,
    hasher: Sha256,
    written: u64,
    limit: u64,
    lock: Option<PathBuf>,
    touched_at: u64,
}

impl<W: Write> HashingWriter<W> {
    fn new(inner: W) -> Self {
        Self {
            inner,
            hasher: Sha256::new(),
            written: 0,
            limit: u64::MAX,
            lock: None,
            touched_at: 0,
        }
    }

    fn bounded(mut self, limit: u64) -> Self {
        self.limit = limit;
        self
    }

    fn touching(mut self, lock: PathBuf) -> Self {
        self.lock = Some(lock);
        self
    }

    fn touch_lock(&mut self) {
        if self.written - self.touched_at < LOCK_TOUCH_BYTES {
            return;
        }
        self.touched_at = self.written;
        if let Some(lock) = &self.lock
            && let Ok(file) = File::options().write(true).open(lock)
        {
            let _ = file.set_modified(SystemTime::now());
        }
    }

    fn finish(mut self) -> Result<(u64, String)> {
        self.inner.flush()?;
        let digest = self.hasher.finalize();
        Ok((
            self.written,
            digest.iter().map(|b| format!("{b:02x}")).collect(),
        ))
    }
}

impl<W: Write> Write for HashingWriter<W> {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        if self.written.saturating_add(buf.len() as u64) > self.limit {
            return Err(std::io::Error::other("larger than the pinned size"));
        }
        let written = self.inner.write(buf)?;
        self.hasher.update(&buf[..written]);
        self.written += written as u64;
        self.touch_lock();
        Ok(written)
    }

    fn flush(&mut self) -> std::io::Result<()> {
        self.inner.flush()
    }
}

/// Lock file held during a download, removed when dropped.
struct DownloadLock {
    path: PathBuf,
}

impl DownloadLock {
    fn acquire(path: &Path) -> Result<Self> {
        for _ in 0..2 {
            match File::options().write(true).create_new(true).open(path) {
                Ok(_) => {
                    return Ok(Self {
                        path: path.to_path_buf(),
                    });
                }
                Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => {
                    if !is_stale(path) {
                        return Err(Error::Model("download already running".into()));
                    }
                    let _ = fs::remove_file(path);
                }
                Err(err) => return Err(err.into()),
            }
        }
        Err(Error::Model("could not take the download lock".into()))
    }
}

impl Drop for DownloadLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

fn is_stale(path: &Path) -> bool {
    fs::metadata(path)
        .and_then(|meta| meta.modified())
        .ok()
        .and_then(|modified| SystemTime::now().duration_since(modified).ok())
        .is_none_or(|age| age > STALE_LOCK)
}

fn env_value(key: &str) -> Option<String> {
    std::env::var(key)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

mod pinned;
pub use pinned::{PinnedFile, PinnedHash, verify_pinned};

#[cfg(test)]
mod tests;
