//! Pipeline sub-commands of the `silicium-raytracer` binary. Each one prints a
//! JSON object on stdout; the exit code is 0 on success, 2 when a verification
//! fails, 1 on invalid input.
//!
//! | Module | Sub-commands |
//! | --- | --- |
//! | `split` | `split` (tile plan of a scene) |
//! | `checks` | `milestones`, `verify`, `validate` |
//! | `reassemble` | `reassemble` (final image) |
//! | `image` | `png` (tile preview), `resolution` (scene size) |
//! | `options` | argument parsing and file helpers |

mod checks;
mod image;
mod options;
mod reassemble;
mod split;

use options::Options;
use serde_json::Value;

/// Names handled here instead of rendering.
pub const NAMES: [&str; 7] = [
    "split",
    "milestones",
    "verify",
    "reassemble",
    "validate",
    "png",
    "resolution",
];

/// Runs a sub-command; returns the JSON to print and the exit code.
pub fn run(name: &str, args: &[String]) -> Result<(Value, i32), String> {
    let options = Options::parse(args)?;
    match name {
        "split" => split::run(&options),
        "milestones" => checks::milestones_command(&options),
        "verify" => checks::verify_command(&options),
        "validate" => checks::validate_command(&options),
        "reassemble" => reassemble::run(&options),
        "png" => image::png_command(&options),
        "resolution" => image::resolution_command(&options),
        other => Err(format!("unknown command {other}")),
    }
}

/// Helpers for the sub-command tests.
#[cfg(test)]
mod tests_support {
    /// Writes `bytes` to a per-process temporary file and returns its path.
    pub fn temp_file(name: &str, bytes: &[u8]) -> String {
        let path =
            std::env::temp_dir().join(format!("silicium-commands-{}-{name}", std::process::id()));
        std::fs::write(&path, bytes).unwrap();
        path.display().to_string()
    }

    /// Owned argument list.
    pub fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| value.to_string()).collect()
    }
}
