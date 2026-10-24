//! `reassemble`: stitches the rendered tiles back into the final image.

use super::image::write_png;
use super::options::{absolute, read, write, Options};
use serde_json::{json, Value};
use silicium_raytracer::pipeline::{reassemble, sha256_hex};
use std::path::Path;

/// `reassemble --fragment a.ppm --x-start X --y-start Y [--fragment ..] --output out.ppm [--png out.png]`.
///
/// The n-th `--x-start` / `--y-start` place the n-th `--fragment` (0 when missing).
pub fn run(options: &Options) -> Result<(Value, i32), String> {
    let fragments = options.all("fragment");
    if fragments.is_empty() {
        return Err("missing --fragment".to_string());
    }
    let images: Vec<Vec<u8>> = fragments
        .iter()
        .map(|path| read(path))
        .collect::<Result<_, _>>()?;
    let (xs, ys) = (options.all("x-start"), options.all("y-start"));
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
    if let Some(png_path) = options.non_empty("png") {
        let fields = write_png(&output, output_path, png_path);
        for key in ["ready", "path", "sha256", "error"] {
            payload[format!("result_png_{key}")] = fields[key].clone();
        }
    }
    Ok((payload, 0))
}

/// Offset of the `index`-th tile, 0 when not given.
fn offset(values: &[String], index: usize) -> Result<usize, String> {
    match values.get(index).map(String::as_str) {
        None | Some("") => Ok(0),
        Some(value) => value
            .parse()
            .map_err(|_| format!("invalid offset: {value}")),
    }
}
