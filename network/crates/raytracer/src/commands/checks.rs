//! Tile checks: `milestones` (commitment), `verify` (probabilistic check) and
//! `validate` (format, size and hash of a rendered tile).

use super::options::{absolute, read, Options};
use serde_json::{json, Value};
use silicium_raytracer::pipeline::{milestones, ppm, sampling};
use std::path::Path;

/// `milestones <tile.ppm> [--y-start Y] [--x-start X] [--batch-rows N]`:
/// pixel hash of every block of rows and the commitment over all of them.
pub fn milestones_command(options: &Options) -> Result<(Value, i32), String> {
    let tile = read(options.input("tile PPM")?)?;
    let manifest = milestones::build(
        &tile,
        options.number("y-start", 0)?,
        options.number("batch-rows", milestones::DEFAULT_VERIFICATION_BATCH_ROWS)?,
        options.number("x-start", 0)?,
    )?;
    let payload = serde_json::to_value(manifest).map_err(|error| error.to_string())?;
    Ok((payload, 0))
}

/// `verify <tile.ppm> --manifest m.json [--seed S] [--reputation R]`:
/// recomputes a sample of milestones (more for a low reputation). Exit code 2
/// when a sampled milestone does not match.
pub fn verify_command(options: &Options) -> Result<(Value, i32), String> {
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
    let payload = serde_json::to_value(result).map_err(|error| error.to_string())?;
    Ok((payload, code))
}

/// `validate <tile.ppm> [--task-id ID] [--width W] [--height H] [--expected-hash H]`:
/// checks a rendered tile (format, size, file hash). `--task-id` labels the
/// error messages (default: the file name). On success the output also carries
/// `pixel_sha256`, the hash of the raster alone used by milestone checks.
pub fn validate_command(options: &Options) -> Result<(Value, i32), String> {
    let path = options.input("tile PPM")?;
    let data = read(path)?;
    let file_name = Path::new(path)
        .file_name()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_default();
    let task_id = options
        .non_empty("task-id")
        .map(str::to_string)
        .unwrap_or(file_name);
    let checked = ppm::validate_fragment(
        &data,
        &task_id,
        options.optional_number("width")?,
        options.optional_number("height")?,
        options.non_empty("expected-hash"),
    );
    match checked {
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

#[cfg(test)]
mod tests {
    use super::super::run;
    use super::super::tests_support::{args, temp_file};
    use silicium_raytracer::pipeline::{ppm, sha256_hex};

    #[test]
    fn validate_reports_both_hashes() {
        let tile = ppm::encode(2, 1, &[1, 2, 3, 4, 5, 6]);
        let path = temp_file("ok.ppm", &tile);
        let (payload, code) =
            run("validate", &args(&[&path, "--width", "2", "--height", "1"])).unwrap();
        assert_eq!(code, 0);
        assert_eq!(payload["sha256"], sha256_hex(&tile));
        assert_eq!(payload["pixel_sha256"], sha256_hex(&[1, 2, 3, 4, 5, 6]));
        assert_eq!(payload["valid_p6"], true);
    }

    #[test]
    fn validate_labels_errors_with_the_task_id() {
        let path = temp_file("bad.ppm", b"not a ppm");
        let (payload, code) = run("validate", &args(&[&path, "--task-id", "task-7"])).unwrap();
        assert_eq!(code, 1);
        let error = payload["error"].as_str().unwrap();
        assert!(
            error.starts_with("raytracer_fragment_invalid_ppm:task=task-7:"),
            "{error}"
        );
    }

    #[test]
    fn verify_passes_a_clean_tile_and_fails_a_tampered_one() {
        let pixels: Vec<u8> = (0..4 * 6 * 3)
            .map(|index| (index * 7 % 256) as u8)
            .collect();
        let clean = ppm::encode(4, 6, &pixels);
        let tile = temp_file("verify-clean.ppm", &clean);
        let (manifest, _) = run("milestones", &args(&[&tile, "--batch-rows", "2"])).unwrap();
        let manifest_path = temp_file("verify-manifest.json", manifest.to_string().as_bytes());
        let verify = |tile: &str| {
            run(
                "verify",
                &args(&[
                    tile,
                    "--manifest",
                    &manifest_path,
                    "--seed",
                    "s",
                    "--reputation",
                    "0",
                ]),
            )
            .unwrap()
        };
        assert_eq!(verify(&tile).1, 0);
        let mut tampered = clean.clone();
        *tampered.last_mut().unwrap() ^= 0xFF;
        let tampered_path = temp_file("verify-tampered.ppm", &tampered);
        let (result, code) = verify(&tampered_path);
        assert_eq!(code, 2);
        assert_eq!(result["verified"], false);
    }
}
