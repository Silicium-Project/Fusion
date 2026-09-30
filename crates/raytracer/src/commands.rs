//! Pipeline sub-commands of the `silicium-raytracer` binary. Each one prints a
//! JSON object on stdout; the exit code is 0 on success, 2 when a verification
//! fails, 1 on invalid input.

use serde_json::{json, Value};
use silicium_raytracer::pipeline::{milestones, png, ppm, reassemble, sampling, sha256_hex, tiles};
use std::{collections::HashMap, fs, path::Path};

/// Names handled here instead of rendering.
pub const NAMES: [&str; 5] = ["split", "milestones", "verify", "reassemble", "validate"];

/// `--key value` options (repeatable) and positional arguments.
struct Options {
    positional: Vec<String>,
    values: HashMap<String, Vec<String>>,
}

impl Options {
    fn parse(args: &[String]) -> Result<Self, String> {
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

    fn one(&self, key: &str) -> Option<&str> {
        self.values
            .get(key)
            .and_then(|values| values.last())
            .map(String::as_str)
    }

    fn all(&self, key: &str) -> Vec<String> {
        self.values.get(key).cloned().unwrap_or_default()
    }

    fn number(&self, key: &str, default: usize) -> Result<usize, String> {
        match self.one(key) {
            None | Some("") => Ok(default),
            Some(value) => value
                .parse()
                .map_err(|_| format!("invalid --{key}: {value}")),
        }
    }

    fn input(&self, what: &str) -> Result<&str, String> {
        self.positional
            .first()
            .map(String::as_str)
            .ok_or_else(|| format!("missing {what}"))
    }
}

fn read(path: &str) -> Result<Vec<u8>, String> {
    fs::read(path).map_err(|error| format!("cannot read {path}: {error}"))
}

fn write(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(path, bytes).map_err(|error| format!("cannot write {}: {error}", path.display()))
}

fn absolute(path: &str) -> String {
    fs::canonicalize(path)
        .map(|path| path.display().to_string())
        .unwrap_or_else(|_| path.to_string())
}

/// Runs a sub-command; returns the JSON to print and the exit code.
pub fn run(name: &str, args: &[String]) -> Result<(Value, i32), String> {
    let options = Options::parse(args)?;
    match name {
        "split" => split(&options),
        "milestones" => {
            let tile = read(options.input("tile PPM")?)?;
            let manifest = milestones::build(
                &tile,
                options.number("y-start", 0)?,
                options.number("batch-rows", milestones::DEFAULT_VERIFICATION_BATCH_ROWS)?,
                options.number("x-start", 0)?,
            )?;
            Ok((
                serde_json::to_value(manifest).map_err(|error| error.to_string())?,
                0,
            ))
        }
        "verify" => {
            let tile = read(options.input("tile PPM")?)?;
            let manifest_path = options.one("manifest").ok_or("missing --manifest")?;
            let manifest: sampling::SampledManifest =
                serde_json::from_slice(&read(manifest_path)?).map_err(|error| error.to_string())?;
            let reputation = match options.one("reputation") {
                Some(value) => value
                    .parse()
                    .map_err(|_| format!("invalid --reputation: {value}"))?,
                None => 50.0,
            };
            let result = sampling::verify(
                &tile,
                &manifest,
                options.one("seed").unwrap_or(""),
                reputation,
            )?;
            let code = if result.verified { 0 } else { 2 };
            Ok((
                serde_json::to_value(result).map_err(|error| error.to_string())?,
                code,
            ))
        }
        "reassemble" => reassemble_command(&options),
        "validate" => validate_command(&options),
        other => Err(format!("unknown command {other}")),
    }
}

/// `validate <tile.ppm> [--task-id ID] [--width W] [--height H] [--expected-hash H]`:
/// checks a rendered tile (format, size, file hash). `--task-id` labels the
/// error messages (default: the file name). On success the output also carries
/// `pixel_sha256`, the hash of the raster alone used by milestone checks.
fn validate_command(options: &Options) -> Result<(Value, i32), String> {
    let path = options.input("tile PPM")?;
    let data = read(path)?;
    let optional = |key: &str| -> Result<Option<usize>, String> {
        options
            .one(key)
            .filter(|value| !value.is_empty())
            .map(|value| {
                value
                    .parse()
                    .map_err(|_| format!("invalid --{key}: {value}"))
            })
            .transpose()
    };
    let file_name = Path::new(path)
        .file_name()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_default();
    let task_id = options
        .one("task-id")
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .unwrap_or(file_name);
    let expected_hash = options
        .one("expected-hash")
        .filter(|value| !value.is_empty());
    match ppm::validate_fragment(
        &data,
        &task_id,
        optional("width")?,
        optional("height")?,
        expected_hash,
    ) {
        Ok((width, height, sha256)) => Ok((
            json!({
                "width": width,
                "height": height,
                "sha256": sha256,
                "pixel_sha256": ppm::pixel_sha256(&data)?,
                "valid_p6": true,
                "fragment": absolute(path),
            }),
            0,
        )),
        Err(error) => Ok((
            json!({"valid": false, "error": error, "fragment": absolute(path)}),
            1,
        )),
    }
}

fn split(options: &Options) -> Result<(Value, i32), String> {
    let scene_path = options.input("scene")?;
    let scene_bytes = read(scene_path)?;
    let (width, height) = tiles::scene_resolution(&String::from_utf8_lossy(&scene_bytes));
    let target = options.number("target-pixels", tiles::DEFAULT_TARGET_PIXELS_PER_FRAGMENT)?;
    let maximum = options.number("max-fragments", tiles::DEFAULT_MAX_FRAGMENTS)?;
    let requested = options.number("fragments", 0)?;
    let count = if requested > 0 {
        requested
    } else {
        tiles::estimate_fragment_count(width, height, target, maximum)
    };
    let scene_sha256 = sha256_hex(&scene_bytes);
    let scene_abs = absolute(scene_path);
    let fragments: Vec<Value> = tiles::split_tiles(width, height, count)?
        .into_iter()
        .enumerate()
        .map(|(index, tile)| {
            json!({
                "fragment_index": index,
                "fragment_id": format!("fragment-{index:03}"),
                "is_leaf": true,
                "depth": 0,
                "tile_row": tile.tile_row,
                "tile_column": tile.tile_column,
                "x_start": tile.x_start,
                "x_end": tile.x_end,
                "y_start": tile.y_start,
                "y_end": tile.y_end,
                "scene_path": scene_abs,
                "scene_sha256": scene_sha256,
                "complexity_score": (tile.x_end - tile.x_start) * (tile.y_end - tile.y_start),
            })
        })
        .collect();
    let payload = json!({
        "schema_version": 1,
        "workload": "raytracer",
        "image": {"width": width, "height": height},
        "split_policy": {
            "kind": "center-out-neighbour-grid",
            "ordering": "breadth-first-edge-neighbours",
            "target_pixels_per_fragment": target,
            "max_fragments": maximum,
        },
        "fragment_count": fragments.len(),
        "fragments": fragments,
    });
    if let Some(output) = options.one("output") {
        let text = serde_json::to_string_pretty(&payload).map_err(|error| error.to_string())?;
        write(Path::new(output), text.as_bytes())?;
    }
    Ok((payload, 0))
}

fn reassemble_command(options: &Options) -> Result<(Value, i32), String> {
    let fragments = options.all("fragment");
    if fragments.is_empty() {
        return Err("missing --fragment".to_string());
    }
    let (xs, ys) = (options.all("x-start"), options.all("y-start"));
    let offset = |values: &[String], index: usize| -> Result<usize, String> {
        match values.get(index).map(String::as_str) {
            None | Some("") => Ok(0),
            Some(value) => value
                .parse()
                .map_err(|_| format!("invalid offset: {value}")),
        }
    };
    let images: Vec<Vec<u8>> = fragments
        .iter()
        .map(|path| read(path))
        .collect::<Result<_, _>>()?;
    let mut placed = Vec::with_capacity(images.len());
    for (index, image) in images.iter().enumerate() {
        placed.push(reassemble::PlacedTile {
            x_start: offset(&xs, index)?,
            y_start: offset(&ys, index)?,
            ppm: image,
        });
    }
    let output_path = options.one("output").ok_or("missing --output")?;
    let output = reassemble::reassemble(&placed)?;
    write(Path::new(output_path), &output)?;
    let mut payload = json!({
        "schema_version": 1,
        "workload": "raytracer",
        "entrypoint": "reassemble",
        "fragment_count": fragments.len(),
        "result_path": absolute(output_path),
        "result_sha256": sha256_hex(&output),
        "result_format": "ppm/p6",
    });
    if let Some(png_path) = options.one("png").filter(|value| !value.is_empty()) {
        let image = ppm::parse(&output, output_path)?;
        let result = png::encode_rgb(image.width, image.height, &image.pixels)
            .and_then(|bytes| write(Path::new(png_path), &bytes).map(|_| bytes));
        let fields = match result {
            Ok(bytes) => {
                json!({"ready": true, "path": absolute(png_path), "sha256": sha256_hex(&bytes), "error": ""})
            }
            Err(error) => json!({"ready": false, "path": "", "sha256": "", "error": error}),
        };
        for key in ["ready", "path", "sha256", "error"] {
            payload[format!("result_png_{key}")] = fields[key].clone();
        }
    }
    Ok((payload, 0))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tile_file(name: &str, bytes: &[u8]) -> String {
        let path =
            std::env::temp_dir().join(format!("silicium-commands-{}-{name}", std::process::id()));
        fs::write(&path, bytes).unwrap();
        path.display().to_string()
    }

    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| value.to_string()).collect()
    }

    #[test]
    fn validate_reports_both_hashes() {
        let tile = ppm::encode(2, 1, &[1, 2, 3, 4, 5, 6]);
        let path = tile_file("ok.ppm", &tile);
        let (payload, code) =
            run("validate", &args(&[&path, "--width", "2", "--height", "1"])).unwrap();
        assert_eq!(code, 0);
        assert_eq!(payload["sha256"], sha256_hex(&tile));
        assert_eq!(payload["pixel_sha256"], sha256_hex(&[1, 2, 3, 4, 5, 6]));
        assert_eq!(payload["valid_p6"], true);
    }

    #[test]
    fn validate_labels_errors_with_the_task_id() {
        let path = tile_file("bad.ppm", b"not a ppm");
        let (payload, code) = run("validate", &args(&[&path, "--task-id", "task-7"])).unwrap();
        assert_eq!(code, 1);
        let error = payload["error"].as_str().unwrap();
        assert!(
            error.starts_with("raytracer_fragment_invalid_ppm:task=task-7:"),
            "{error}"
        );
    }
}
