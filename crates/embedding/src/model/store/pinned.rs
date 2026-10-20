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

    fn store_name(&self) -> String {
        match self.hash {
            PinnedHash::Sha256(hash) => hash.to_string(),
            PinnedHash::GitBlob(hash) => format!("git-{hash}"),
        }
    }
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
        let path = self.pinned_path(file)?;
        fs::create_dir_all(&self.root)?;
        if path.exists() {
            if verify_pinned(&path, file).is_ok() {
                return Ok(path);
            }
            fs::remove_file(&path)?;
        }
        let url = format!(
            "{}/{}/resolve/{}/{}",
            self.base_url, repository, revision, file.path
        );
        let lock = DownloadLock::acquire(&path.with_extension("lock"))?;
        let partial = path.with_extension("partial");
        let mut sink = PinnedWriter::new(File::create(&partial)?, file);
        let fetched = self.fetcher.fetch(&url, &mut sink);
        let checked = fetched.and_then(|()| sink.finish(file));
        drop(lock);
        if let Err(err) = checked {
            let _ = fs::remove_file(&partial);
            return Err(err);
        }
        fs::rename(&partial, &path)?;
        Ok(path)
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
}
