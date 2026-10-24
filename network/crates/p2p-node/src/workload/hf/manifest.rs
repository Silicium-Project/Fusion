//! The model manifest (`silicium-model/1`) written by the BackEnd's
//! catalogue (`internal/catalog`): a repository of the Hugging Face Hub at
//! one commit, the files the runtime reads with their hashes, and how to
//! load the model.
//!
//! The node never trusts it blindly: [`Manifest::check`] recomputes its
//! digest (the JSON the BackEnd hashed: fields in this order, empty optional
//! fields left out) and applies the safety rules again (paths, formats,
//! runtime, size). The files are then checked by hash when downloaded.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use silicium_embedding::model::store::{PinnedFile, PinnedHash};

pub(crate) const FORMAT: &str = "silicium-model/1";

/// Largest model this node accepts (`SILICIUM_AI_MAX_MODEL_GB`, default 24).
const DEFAULT_MAX_MODEL_GB: u64 = 24;

/// Libraries the Silicium AI runtime loads for the tasks of this workload.
const LIBRARIES: &[&str] = &["transformers", "sentence-transformers", "timm"];

/// Extensions never accepted in a manifest: code, and formats whose loading
/// runs code (Python pickle).
const FORBIDDEN_EXTENSIONS: &[&str] = &[
    "py", "pyc", "so", "dll", "dylib", "exe", "sh", "bat", "bin", "pt", "pth", "pkl", "pickle",
    "joblib", "ckpt", "h5", "msgpack",
];

fn is_empty(value: &str) -> bool {
    value.is_empty()
}

fn is_zero(value: &u64) -> bool {
    *value == 0
}

fn is_false(value: &bool) -> bool {
    !*value
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct ManifestFile {
    pub(crate) path: String,
    pub(crate) size: u64,
    #[serde(default, skip_serializing_if = "is_empty")]
    pub(crate) sha256: String,
    #[serde(default, skip_serializing_if = "is_empty")]
    pub(crate) git_oid: String,
}

impl ManifestFile {
    /// The file as the model store pins it.
    pub(crate) fn pinned(&self) -> PinnedFile<'_> {
        PinnedFile {
            path: &self.path,
            size: self.size,
            hash: if self.sha256.is_empty() {
                PinnedHash::GitBlob(&self.git_oid)
            } else {
                PinnedHash::Sha256(&self.sha256)
            },
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct Loader {
    #[serde(default, skip_serializing_if = "is_empty")]
    pub(crate) auto_model: String,
    #[serde(default, skip_serializing_if = "is_empty")]
    pub(crate) processor: String,
    #[serde(default, skip_serializing_if = "is_empty")]
    pub(crate) pipeline_class: String,
    #[serde(default, skip_serializing_if = "is_empty")]
    pub(crate) model_type: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub(crate) architectures: Vec<String>,
    #[serde(default, skip_serializing_if = "is_empty")]
    pub(crate) variant: String,
}

/// Field order and omissions follow the BackEnd's `catalog.Manifest`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct Manifest {
    pub(crate) format: String,
    pub(crate) key: String,
    pub(crate) digest: String,
    pub(crate) repository: String,
    pub(crate) revision: String,
    pub(crate) task: String,
    pub(crate) library: String,
    pub(crate) runtime: String,
    pub(crate) loader: Loader,
    pub(crate) files: Vec<ManifestFile>,
    pub(crate) total_bytes: u64,
    #[serde(default, skip_serializing_if = "is_zero")]
    pub(crate) parameters: u64,
    pub(crate) hardware_class: String,
    pub(crate) licence: String,
    #[serde(default, skip_serializing_if = "is_false")]
    pub(crate) custom_code_declared: bool,
}

impl Manifest {
    /// The digest of the manifest without its key and digest.
    pub(crate) fn computed_digest(&self) -> String {
        let mut unsealed = self.clone();
        unsealed.key.clear();
        unsealed.digest.clear();
        let encoded = serde_json::to_vec(&unsealed).expect("a manifest serializes");
        hex(&Sha256::digest(&encoded))
    }

    /// Sets the digest and the key, as the BackEnd does (tests).
    #[cfg(test)]
    pub(crate) fn seal(&mut self) {
        self.digest = self.computed_digest();
        self.key = format!("{}-{}", slug(&self.repository), &self.digest[..12]);
    }

    /// Checks the digest, the key and the safety rules; the error says why
    /// the model is refused.
    pub(crate) fn check(&self) -> Result<(), String> {
        if self.format != FORMAT {
            return Err(format!("unknown manifest format {}", self.format));
        }
        let digest = self.computed_digest();
        if digest != self.digest {
            return Err("manifest digest mismatch".into());
        }
        let expected_key = format!("{}-{}", slug(&self.repository), &digest[..12]);
        if self.key != expected_key {
            return Err("manifest key mismatch".into());
        }
        if !valid_repository(&self.repository) || !is_hex(&self.revision, 40) {
            return Err("invalid repository or revision".into());
        }
        if self.runtime != "python" || !LIBRARIES.contains(&self.library.as_str()) {
            return Err(format!(
                "runtime {} / library {} not run by this workload",
                self.runtime, self.library
            ));
        }
        if self.files.is_empty() {
            return Err("manifest without files".into());
        }
        let mut total: u64 = 0;
        for file in &self.files {
            if !safe_path(&file.path) {
                return Err(format!("unsafe path {:?}", file.path));
            }
            let extension = file
                .path
                .rsplit_once('.')
                .map(|(_, extension)| extension.to_ascii_lowercase())
                .unwrap_or_default();
            if FORBIDDEN_EXTENSIONS.contains(&extension.as_str()) {
                return Err(format!("forbidden file {}", file.path));
            }
            let hashed = match (file.sha256.is_empty(), file.git_oid.is_empty()) {
                (false, true) => is_hex(&file.sha256, 64),
                (true, false) => is_hex(&file.git_oid, 40),
                _ => false,
            };
            if !hashed {
                return Err(format!("file {} without a valid hash", file.path));
            }
            total = total.saturating_add(file.size);
        }
        if total != self.total_bytes {
            return Err("total size mismatch".into());
        }
        if total > max_model_bytes() {
            return Err("model larger than this node accepts".into());
        }
        Ok(())
    }
}

fn max_model_bytes() -> u64 {
    std::env::var("SILICIUM_AI_MAX_MODEL_GB")
        .ok()
        .and_then(|value| value.trim().parse::<u64>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(DEFAULT_MAX_MODEL_GB)
        .saturating_mul(1 << 30)
}

pub(crate) fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn is_hex(value: &str, len: usize) -> bool {
    value.len() == len
        && value
            .bytes()
            .all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

fn valid_repository(repository: &str) -> bool {
    let parts: Vec<&str> = repository.split('/').collect();
    (1..=2).contains(&parts.len())
        && parts.iter().all(|part| {
            !part.is_empty()
                && part.len() <= 96
                && part
                    .chars()
                    .next()
                    .is_some_and(|c| c.is_ascii_alphanumeric())
                && part
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '-'))
        })
}

/// The repository part of a model key (`owner--name`), as the BackEnd
/// writes it.
fn slug(repository: &str) -> String {
    let lowered = repository.to_lowercase().replace('/', "--");
    let mut value = String::with_capacity(lowered.len());
    let mut in_invalid = false;
    for c in lowered.chars() {
        if c.is_ascii_lowercase() || c.is_ascii_digit() || matches!(c, '.' | '_' | '-') {
            value.push(c);
            in_invalid = false;
        } else if !in_invalid {
            value.push('-');
            in_invalid = true;
        }
    }
    if value.len() > 80 {
        value.truncate(80);
    }
    value.trim_matches(|c| c == '-' || c == '.').to_string()
}

/// A relative path whose every part is a plain name (no `..`, no hidden
/// file, no drive or separator of another OS).
pub(crate) fn safe_path(path: &str) -> bool {
    !path.is_empty()
        && path.len() <= 300
        && !path.starts_with('/')
        && !path.contains(['\\', ':', '\0', '"'])
        && path.chars().all(|c| c.is_ascii_graphic() || c == ' ')
        && path
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != ".." && !part.starts_with('.'))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The BackEnd's image classifier fixture (`internal/catalog`,
    /// `golden_test.go`): the same JSON must give the same digest here.
    pub(crate) const GOLDEN: &str = r#"{"format":"silicium-model/1","key":"google--vit-base-patch16-224-0ff8e2804e7f","digest":"0ff8e2804e7f301e0048936ce90e42a221f52eb5e9bc5b34e5ba74f59e8da9ff","repository":"google/vit-base-patch16-224","revision":"3f49326eb077187dfe1c2a2bb15fbd74e6ab91e3","task":"image-classification","library":"transformers","runtime":"python","loader":{"auto_model":"AutoModelForImageClassification","processor":"AutoImageProcessor","model_type":"vit","architectures":["ViTForImageClassification"]},"files":[{"path":"config.json","size":1983,"git_oid":"3333333333333333333333333333333333333333"},{"path":"model.safetensors","size":346293852,"sha256":"5555555555555555555555555555555555555555555555555555555555555555"},{"path":"preprocessor_config.json","size":1983,"git_oid":"6666666666666666666666666666666666666666"}],"total_bytes":346297818,"parameters":86567656,"hardware_class":"A","licence":"apache-2.0"}"#;

    fn golden() -> Manifest {
        serde_json::from_str(GOLDEN).unwrap()
    }

    #[test]
    fn digest_matches_the_backend() {
        let manifest = golden();
        assert_eq!(manifest.computed_digest(), manifest.digest);
        assert_eq!(serde_json::to_string(&manifest).unwrap(), GOLDEN);
        manifest.check().unwrap();
    }

    #[test]
    fn a_changed_manifest_is_refused() {
        let mut manifest = golden();
        manifest.files[1].sha256 = "6".repeat(64);
        assert!(manifest.check().unwrap_err().contains("digest"));

        let mut manifest = golden();
        manifest.key = "someone--else-0ff8e2804e7f".into();
        assert!(manifest.check().unwrap_err().contains("key"));
    }

    fn resealed(change: impl FnOnce(&mut Manifest)) -> Manifest {
        let mut manifest = golden();
        change(&mut manifest);
        manifest.total_bytes = manifest.files.iter().map(|f| f.size).sum();
        manifest.digest = manifest.computed_digest();
        manifest.key = format!("{}-{}", slug(&manifest.repository), &manifest.digest[..12]);
        manifest
    }

    #[test]
    fn safety_rules_apply_even_to_a_well_sealed_manifest() {
        let pickle = resealed(|m| m.files[1].path = "pytorch_model.bin".into());
        assert!(pickle.check().unwrap_err().contains("forbidden"));
        let code = resealed(|m| m.files[0].path = "modeling.py".into());
        assert!(code.check().unwrap_err().contains("forbidden"));
        let escape = resealed(|m| m.files[0].path = "../config.json".into());
        assert!(escape.check().unwrap_err().contains("unsafe"));
        let hidden = resealed(|m| m.files[0].path = "a/.git/config".into());
        assert!(hidden.check().unwrap_err().contains("unsafe"));
        let ollama = resealed(|m| m.runtime = "ollama".into());
        assert!(ollama.check().is_err());
        let no_hash = resealed(|m| m.files[0].git_oid = "zz".into());
        assert!(no_hash.check().unwrap_err().contains("hash"));
        resealed(|m| m.files[0].path = "1_Pooling/config.json".into())
            .check()
            .unwrap();
    }

    #[test]
    fn slug_matches_the_backend() {
        assert_eq!(
            slug("google/vit-base-patch16-224"),
            "google--vit-base-patch16-224"
        );
        assert_eq!(slug("Org/Model_V2.1"), "org--model_v2.1");
    }
}
