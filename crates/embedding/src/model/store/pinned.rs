//! Files pinned by a model manifest of the Hugging Face catalogue
//! (`ai/hf/…` workloads): any file of a repository at one commit, checked
//! either by the SHA-256 of its content (large files, which the Hub stores
//! with LFS) or by its git blob hash (small files, for which the Hub gives
//! no SHA-256).
//!
//! They live in the same store as the other model files: `<root>/<sha256>`
//! or `<root>/git-<sha1>`, written complete and checked, with the same lock
//! and the same source (`SILICIUM_MODEL_BASE_URL`).

use super::{DownloadLock, ModelStore};
use crate::{Error, Result};
use sha1::Sha1;
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File},
    io::Write,
    path::{Path, PathBuf},
};

/// How a pinned file is checked.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PinnedHash<'a> {
    /// SHA-256 of the content (lowercase hex).
    Sha256(&'a str),
    /// Git blob hash: SHA-1 of `blob <size>\0<content>` (lowercase hex).
    GitBlob(&'a str),
}

/// A file of a repository at a commit.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PinnedFile<'a> {
    /// Path inside the repository.
    pub path: &'a str,
    pub size: u64,
    pub hash: PinnedHash<'a>,
}

fn is_hex(value: &str, len: usize) -> bool {
    value.len() == len
        && value
            .bytes()
            .all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

impl PinnedFile<'_> {
    fn check_form(&self) -> Result<()> {
        let valid = match self.hash {
            PinnedHash::Sha256(hash) => is_hex(hash, 64),
            PinnedHash::GitBlob(hash) => is_hex(hash, 40),
        };
        if !valid {
            return Err(Error::Model(format!("{}: invalid hash", self.path)));
        }
        Ok(())
    }

    /// Name of the file in the store: `<sha256>` or `git-<sha1>` (also its
    /// name between peers, which serve the store to each other).
    pub fn store_name(&self) -> String {
        match self.hash {
            PinnedHash::Sha256(hash) => hash.to_string(),
            PinnedHash::GitBlob(hash) => format!("git-{hash}"),
        }
    }
}

/// Why a pinned file could not be fetched from the Hub.
#[derive(Debug)]
pub enum PinnedFetchError {
    /// The Hub could not be reached or refused the download.
    Unavailable(Error),
    /// The Hub sent a file that is not the pinned one (other size or hash):
    /// the repository changed under the pinned commit, or the source is
    /// wrong.
    Mismatch(Error),
}

impl From<PinnedFetchError> for Error {
    fn from(err: PinnedFetchError) -> Self {
        match err {
            PinnedFetchError::Unavailable(err) | PinnedFetchError::Mismatch(err) => err,
        }
    }
}

/// True for the name of a pinned file in the store (`<sha256>` or
/// `git-<sha1>`), the only names served to peers.
pub fn is_pinned_name(name: &str) -> bool {
    is_hex(name, 64)
        || name
            .strip_prefix("git-")
            .is_some_and(|hash| is_hex(hash, 40))
}

impl ModelStore {
    /// Where the pinned `file` is (or will be).
    pub fn pinned_path(&self, file: &PinnedFile) -> Result<PathBuf> {
        file.check_form()?;
        Ok(self.root.join(file.store_name()))
    }

    /// True when `file` is here with its pinned size (the hash is checked
    /// by [`ModelStore::ensure_pinned`]).
    pub fn has_pinned(&self, file: &PinnedFile) -> bool {
        self.pinned_path(file)
            .ok()
            .and_then(|path| fs::metadata(path).ok())
            .is_some_and(|meta| meta.len() == file.size)
    }

    /// Downloads `file` of `repository` at `revision` unless it is already
    /// here and intact, and returns its path.
    pub fn ensure_pinned(
        &self,
        repository: &str,
        revision: &str,
        file: &PinnedFile,
    ) -> Result<PathBuf> {
        Ok(self.fetch_pinned(repository, revision, file)?)
    }

    /// The path of `file` when it is here and intact (a damaged copy is
    /// removed).
    pub fn intact_pinned(&self, file: &PinnedFile) -> Result<Option<PathBuf>> {
        let path = self.pinned_path(file)?;
        if !path.exists() {
            return Ok(None);
        }
        if verify_pinned(&path, file).is_ok() {
            return Ok(Some(path));
        }
        fs::remove_file(&path)?;
        Ok(None)
    }

    /// Like [`ModelStore::ensure_pinned`], telling a file the Hub could not
    /// send from a file that is not the pinned one.
    pub fn fetch_pinned(
        &self,
        repository: &str,
        revision: &str,
        file: &PinnedFile,
    ) -> std::result::Result<PathBuf, PinnedFetchError> {
        let path = self
            .pinned_path(file)
            .map_err(PinnedFetchError::Unavailable)?;
        fs::create_dir_all(&self.root).map_err(|err| PinnedFetchError::Unavailable(err.into()))?;
        if let Some(path) = self
            .intact_pinned(file)
            .map_err(PinnedFetchError::Unavailable)?
        {
            return Ok(path);
        }
        let url = format!(
            "{}/{}/resolve/{}/{}",
            self.base_url, repository, revision, file.path
        );
        let unavailable = |err: Error| PinnedFetchError::Unavailable(err);
        let lock = DownloadLock::acquire(&path.with_extension("lock")).map_err(unavailable)?;
        let partial = path.with_extension("partial");
        let created = File::create(&partial).map_err(|err| unavailable(err.into()))?;
        let mut sink = PinnedWriter::new(created, file);
        let checked = match self.fetcher.fetch(&url, &mut sink) {
            Ok(()) => sink.finish(file).map_err(PinnedFetchError::Mismatch),
            Err(err) if sink.oversized => Err(PinnedFetchError::Mismatch(err)),
            Err(err) => Err(PinnedFetchError::Unavailable(err)),
        };
        drop(lock);
        if let Err(err) = checked {
            let _ = fs::remove_file(&partial);
            return Err(err);
        }
        fs::rename(&partial, &path).map_err(|err| unavailable(err.into()))?;
        Ok(path)
    }

    /// Where a copy of `file` received from peers is written before
    /// [`ModelStore::install_pinned`] checks it.
    pub fn peer_partial_path(&self, file: &PinnedFile) -> Result<PathBuf> {
        let path = self.pinned_path(file)?;
        fs::create_dir_all(&self.root)?;
        Ok(path.with_extension("peer"))
    }

    /// Checks `received` (a copy of `file` from a peer) against the pinned
    /// size and hash and moves it into the store; removes it otherwise.
    pub fn install_pinned(&self, file: &PinnedFile, received: &Path) -> Result<PathBuf> {
        let path = self.pinned_path(file)?;
        if let Err(err) = verify_pinned(received, file) {
            let _ = fs::remove_file(received);
            return Err(err);
        }
        let lock = DownloadLock::acquire(&path.with_extension("lock"))?;
        let moved = fs::rename(received, &path);
        drop(lock);
        moved?;
        Ok(path)
    }

    /// Names and sizes of the complete pinned files of the store.
    pub fn pinned_files(&self) -> Vec<(String, u64)> {
        let Ok(entries) = fs::read_dir(&self.root) else {
            return Vec::new();
        };
        let mut files: Vec<(String, u64)> = entries
            .flatten()
            .filter_map(|entry| {
                let name = entry.file_name().into_string().ok()?;
                let meta = entry.metadata().ok()?;
                (is_pinned_name(&name) && meta.is_file()).then_some((name, meta.len()))
            })
            .collect();
        files.sort();
        files
    }

    /// Path of the pinned file named `name` (see [`is_pinned_name`]), when
    /// it is in the store.
    pub fn pinned_file_by_name(&self, name: &str) -> Option<PathBuf> {
        let path = self.root.join(name);
        (is_pinned_name(name) && path.is_file()).then_some(path)
    }
}

/// Checks a file on disk against its pinned size and hash.
pub fn verify_pinned(path: &Path, file: &PinnedFile) -> Result<()> {
    file.check_form()?;
    let mut source =
        File::open(path).map_err(|err| Error::Model(format!("{} missing: {err}", file.path)))?;
    let mut sink = PinnedWriter::new(std::io::sink(), file);
    if std::io::copy(&mut source, &mut sink).is_err() {
        return Err(Error::Model(format!("{} is larger than pinned", file.path)));
    }
    sink.finish(file)
}

enum Hasher {
    Sha256(Sha256),
    GitBlob(Sha1),
}

/// Writes through while hashing, and refuses to go past the pinned size.
struct PinnedWriter<W: Write> {
    inner: W,
    hasher: Hasher,
    written: u64,
    limit: u64,
    /// The source sent more than the pinned size.
    oversized: bool,
}

impl<W: Write> PinnedWriter<W> {
    fn new(inner: W, file: &PinnedFile) -> Self {
        let hasher = match file.hash {
            PinnedHash::Sha256(_) => Hasher::Sha256(Sha256::new()),
            PinnedHash::GitBlob(_) => {
                let mut sha1 = Sha1::new();
                sha1.update(format!("blob {}\0", file.size).as_bytes());
                Hasher::GitBlob(sha1)
            }
        };
        Self {
            inner,
            hasher,
            written: 0,
            limit: file.size,
            oversized: false,
        }
    }

    fn finish(mut self, file: &PinnedFile) -> Result<()> {
        self.inner.flush()?;
        let (got, expected) = match (self.hasher, file.hash) {
            (Hasher::Sha256(hasher), PinnedHash::Sha256(expected)) => {
                (hex(&hasher.finalize()), expected)
            }
            (Hasher::GitBlob(hasher), PinnedHash::GitBlob(expected)) => {
                (hex(&hasher.finalize()), expected)
            }
            _ => return Err(Error::Model("hash kind mismatch".into())),
        };
        if self.written != file.size || got != expected {
            return Err(Error::Model(format!(
                "{}: got {} bytes hashing to {got}, expected {} bytes hashing to {expected}",
                file.path, self.written, file.size
            )));
        }
        Ok(())
    }
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

impl<W: Write> Write for PinnedWriter<W> {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        if self.written.saturating_add(buf.len() as u64) > self.limit {
            self.oversized = true;
            return Err(std::io::Error::other("larger than the pinned size"));
        }
        let written = self.inner.write(buf)?;
        match &mut self.hasher {
            Hasher::Sha256(hasher) => hasher.update(&buf[..written]),
            Hasher::GitBlob(hasher) => hasher.update(&buf[..written]),
        }
        self.written += written as u64;
        Ok(written)
    }

    fn flush(&mut self) -> std::io::Result<()> {
        self.inner.flush()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::store::Fetcher;
    use std::sync::{Arc, Mutex};

    struct Serve(Arc<Mutex<Vec<String>>>, &'static [u8]);

    impl Fetcher for Serve {
        fn fetch(&self, url: &str, sink: &mut dyn Write) -> Result<()> {
            self.0.lock().unwrap().push(url.to_string());
            sink.write_all(self.1)
                .map_err(|err| Error::Model(err.to_string()))
        }
    }

    fn store(name: &str, body: &'static [u8]) -> (ModelStore, Arc<Mutex<Vec<String>>>) {
        let root =
            std::env::temp_dir().join(format!("silicium-pinned-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        let urls = Arc::new(Mutex::new(Vec::new()));
        let store = ModelStore::new(
            root,
            "https://hub.example/",
            Box::new(Serve(urls.clone(), body)),
        );
        (store, urls)
    }

    // `printf 'hello\n' | git hash-object --stdin`
    const HELLO_GIT: &str = "ce013625030ba8dba906f756967f9e9ca394464a";
    const HELLO_SHA256: &str = "5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03";

    #[test]
    fn git_blob_and_sha256_files_are_checked() {
        let (store, urls) = store("ok", b"hello\n");
        let git = PinnedFile {
            path: "config.json",
            size: 6,
            hash: PinnedHash::GitBlob(HELLO_GIT),
        };
        let path = store.ensure_pinned("org/model", "abc", &git).unwrap();
        assert!(path.ends_with(format!("git-{HELLO_GIT}")));
        assert_eq!(
            urls.lock().unwrap()[0],
            "https://hub.example/org/model/resolve/abc/config.json"
        );
        let lfs = PinnedFile {
            path: "sub/model.safetensors",
            size: 6,
            hash: PinnedHash::Sha256(HELLO_SHA256),
        };
        store.ensure_pinned("org/model", "abc", &lfs).unwrap();
        assert!(store.has_pinned(&git) && store.has_pinned(&lfs));
        // Already here: not downloaded again.
        store.ensure_pinned("org/model", "abc", &git).unwrap();
        assert_eq!(urls.lock().unwrap().len(), 2);
    }

    #[test]
    fn a_file_with_another_content_is_refused() {
        let (store, _) = store("bad", b"hellO\n");
        let git = PinnedFile {
            path: "config.json",
            size: 6,
            hash: PinnedHash::GitBlob(HELLO_GIT),
        };
        assert!(store.ensure_pinned("org/model", "abc", &git).is_err());
        assert!(!store.has_pinned(&git));
        let bad_form = PinnedFile {
            path: "x",
            size: 1,
            hash: PinnedHash::Sha256("../../etc"),
        };
        assert!(store.pinned_path(&bad_form).is_err());
    }

    #[test]
    fn a_wrong_file_from_the_hub_is_told_apart_from_an_unreachable_hub() {
        let (wrong, _) = store("mismatch", b"other\n");
        let lfs = PinnedFile {
            path: "model.safetensors",
            size: 6,
            hash: PinnedHash::Sha256(HELLO_SHA256),
        };
        assert!(matches!(
            wrong.fetch_pinned("org/model", "abc", &lfs),
            Err(PinnedFetchError::Mismatch(_))
        ));
        let (larger, _) = store("larger", b"hello world\n");
        assert!(matches!(
            larger.fetch_pinned("org/model", "abc", &lfs),
            Err(PinnedFetchError::Mismatch(_))
        ));
        assert!(larger.pinned_files().is_empty(), "nothing kept");
    }

    #[test]
    fn a_copy_from_a_peer_is_checked_before_it_is_kept() {
        let (store, urls) = store("peer", b"unused");
        let lfs = PinnedFile {
            path: "model.safetensors",
            size: 6,
            hash: PinnedHash::Sha256(HELLO_SHA256),
        };
        let received = store.peer_partial_path(&lfs).unwrap();
        fs::write(&received, b"wrong\n").unwrap();
        assert!(store.install_pinned(&lfs, &received).is_err());
        assert!(!received.exists() && !store.has_pinned(&lfs));
        fs::write(&received, b"hello\n").unwrap();
        let path = store.install_pinned(&lfs, &received).unwrap();
        assert_eq!(store.intact_pinned(&lfs).unwrap(), Some(path.clone()));
        assert_eq!(store.pinned_files(), vec![(HELLO_SHA256.to_string(), 6)]);
        assert_eq!(store.pinned_file_by_name(HELLO_SHA256), Some(path));
        assert_eq!(store.pinned_file_by_name("../etc/passwd"), None);
        assert!(urls.lock().unwrap().is_empty(), "the Hub was not asked");
    }

    #[test]
    fn only_store_names_are_served() {
        assert!(is_pinned_name(HELLO_SHA256));
        assert!(is_pinned_name(&format!("git-{HELLO_GIT}")));
        for name in [
            "",
            "git-",
            "x.partial",
            &format!("{HELLO_SHA256}.lock"),
            "../git-a",
        ] {
            assert!(!is_pinned_name(name), "{name}");
        }
    }
}
