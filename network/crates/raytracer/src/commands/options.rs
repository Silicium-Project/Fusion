//! Argument parsing and file helpers shared by the pipeline sub-commands.

use std::{collections::HashMap, fs, path::Path};

/// `--key value` options (repeatable) and positional arguments.
pub struct Options {
    positional: Vec<String>,
    values: HashMap<String, Vec<String>>,
}

impl Options {
    /// Splits `args` into positional arguments and `--key value` pairs.
    pub fn parse(args: &[String]) -> Result<Self, String> {
        let mut options = Options {
            positional: Vec::new(),
            values: HashMap::new(),
        };
        let mut index = 0;
        while index < args.len() {
            let arg = &args[index];
            if let Some(key) = arg.strip_prefix("--") {
                let value = args
                    .get(index + 1)
                    .ok_or_else(|| format!("missing value for {arg}"))?;
                options
                    .values
                    .entry(key.to_string())
                    .or_default()
                    .push(value.clone());
                index += 2;
            } else {
                options.positional.push(arg.clone());
                index += 1;
            }
        }
        Ok(options)
    }

    /// Last value given for `--key`.
    pub fn one(&self, key: &str) -> Option<&str> {
        self.values
            .get(key)
            .and_then(|values| values.last())
            .map(String::as_str)
    }

    /// Last non-empty value given for `--key`.
    pub fn non_empty(&self, key: &str) -> Option<&str> {
        self.one(key).filter(|value| !value.is_empty())
    }

    /// Every value given for a repeatable `--key`, in order.
    pub fn all(&self, key: &str) -> Vec<String> {
        self.values.get(key).cloned().unwrap_or_default()
    }

    /// `--key` as a number, `default` when absent or empty.
    pub fn number(&self, key: &str, default: usize) -> Result<usize, String> {
        Ok(self.optional_number(key)?.unwrap_or(default))
    }

    /// `--key` as a number, `None` when absent or empty.
    pub fn optional_number(&self, key: &str) -> Result<Option<usize>, String> {
        self.non_empty(key)
            .map(|value| {
                value
                    .parse()
                    .map_err(|_| format!("invalid --{key}: {value}"))
            })
            .transpose()
    }

    /// First positional argument (the input file), `what` names it in errors.
    pub fn input(&self, what: &str) -> Result<&str, String> {
        self.positional
            .first()
            .map(String::as_str)
            .ok_or_else(|| format!("missing {what}"))
    }
}

/// Reads a whole file.
pub fn read(path: &str) -> Result<Vec<u8>, String> {
    fs::read(path).map_err(|error| format!("cannot read {path}: {error}"))
}

/// Writes a whole file, creating its parent directories.
pub fn write(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(path, bytes).map_err(|error| format!("cannot write {}: {error}", path.display()))
}

/// Absolute form of `path` when it exists, `path` unchanged otherwise.
pub fn absolute(path: &str) -> String {
    fs::canonicalize(path)
        .map(|path| path.display().to_string())
        .unwrap_or_else(|_| path.to_string())
}
