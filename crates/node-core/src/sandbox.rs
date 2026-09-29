//! Confinement of file paths that come from the network or from a local API.
//!
//! A peer must never choose which file of the host is read or overwritten:
//! every such path is a *relative* path, resolved inside a directory owned by
//! the node (its data directory or a work directory).

use std::path::{Component, Path, PathBuf};

/// Why a path was refused.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum SandboxError {
    #[error("sandbox_path_empty")]
    Empty,
    #[error("sandbox_path_not_relative:{0}")]
    NotRelative(String),
    #[error("sandbox_path_escapes_root:{0}")]
    Escapes(String),
}

/// Checks that `relative` is a plain relative path (no root, no drive prefix,
/// no `..`) and returns it joined to `root`.
///
/// This is a lexical check: callers that write files must also make sure
/// `root` itself is a directory they created (no pre-existing symlinks from
/// untrusted sources inside it).
pub fn resolve(root: &Path, relative: &str) -> Result<PathBuf, SandboxError> {
    let trimmed = relative.trim();
    if trimmed.is_empty() {
        return Err(SandboxError::Empty);
    }
    // Windows-style absolute paths and UNC paths are refused on every OS.
    let bytes = trimmed.as_bytes();
    if trimmed.starts_with('/')
        || trimmed.starts_with('\\')
        || (bytes.len() >= 2 && bytes[1] == b':')
    {
        return Err(SandboxError::NotRelative(trimmed.to_string()));
    }
    let normalized = trimmed.replace('\\', "/");
    let mut resolved = root.to_path_buf();
    for component in Path::new(&normalized).components() {
        match component {
            Component::Normal(part) => resolved.push(part),
            Component::CurDir => {}
            Component::ParentDir => return Err(SandboxError::Escapes(trimmed.to_string())),
            Component::RootDir | Component::Prefix(_) => {
                return Err(SandboxError::NotRelative(trimmed.to_string()));
            }
        }
    }
    if resolved == root {
        return Err(SandboxError::Empty);
    }
    Ok(resolved)
}

/// Keeps only `[A-Za-z0-9._-]` so an identifier can be used as one path
/// component (at most 128 characters).
pub fn safe_component(value: &str) -> Option<String> {
    let cleaned: String = value
        .chars()
        .filter(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | '-')
        })
        .take(128)
        .collect();
    if cleaned.is_empty() || cleaned.chars().all(|character| character == '.') {
        None
    } else {
        Some(cleaned)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn relative_paths_stay_inside_the_root() {
        let root = Path::new("/data/work");
        assert_eq!(
            resolve(root, "scenes/a.cfg").unwrap(),
            root.join("scenes").join("a.cfg")
        );
        assert_eq!(resolve(root, "./a.cfg").unwrap(), root.join("a.cfg"));
        assert_eq!(
            resolve(root, "dir\\b.cfg").unwrap(),
            root.join("dir").join("b.cfg")
        );
    }

    #[test]
    fn escapes_and_absolute_paths_are_refused() {
        let root = Path::new("/data/work");
        for bad in [
            "",
            "  ",
            ".",
            "../etc/passwd",
            "a/../../b",
            "/etc/passwd",
            "\\\\server\\share",
            "C:\\Windows",
            "c:/x",
        ] {
            assert!(resolve(root, bad).is_err(), "{bad:?} must be refused");
        }
    }

    #[test]
    fn identifiers_become_single_components() {
        assert_eq!(
            safe_component("job-42/frag:007").as_deref(),
            Some("job-42frag007")
        );
        assert_eq!(safe_component("../.."), None);
        assert_eq!(safe_component(""), None);
    }
}
