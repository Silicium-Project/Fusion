//! Image helpers: `png` (preview of a tile) and `resolution` (size declared by a scene).

use super::options::{absolute, read, write, Options};
use serde_json::{json, Value};
use silicium_raytracer::pipeline::{png, ppm, sha256_hex, tiles};
use std::path::Path;

/// `png <tile.ppm> --output <preview.png>`: converts a P6 tile to PNG.
///
/// Prints `{ready, path, sha256, error}`; exit code 1 (and no file left
/// behind) when the tile cannot be converted.
pub fn png_command(options: &Options) -> Result<(Value, i32), String> {
    let input = options.input("tile PPM")?;
    let output = options.non_empty("output").ok_or("missing --output")?;
    let fields = write_png(&read(input)?, input, output);
    let code = if fields["ready"] == true { 0 } else { 1 };
    Ok((fields, code))
}

/// Writes `ppm_bytes` as a PNG at `output` and describes the result as
/// `{ready, path, sha256, error}` (also used by `reassemble --png`).
pub fn write_png(ppm_bytes: &[u8], source: &str, output: &str) -> Value {
    let result = ppm::parse(ppm_bytes, source)
        .and_then(|image| png::encode_rgb(image.width, image.height, &image.pixels))
        .and_then(|bytes| write(Path::new(output), &bytes).map(|_| bytes));
    match result {
        Ok(bytes) => {
            json!({"ready": true, "path": absolute(output), "sha256": sha256_hex(&bytes), "error": ""})
        }
        Err(error) => {
            let _ = std::fs::remove_file(output);
            json!({"ready": false, "path": "", "sha256": "", "error": error})
        }
    }
}

/// `resolution <scene.cfg>`: `{width, height}` declared by the scene
/// (1920x1080 when the scene does not say).
pub fn resolution_command(options: &Options) -> Result<(Value, i32), String> {
    let scene = read(options.input("scene")?)?;
    let (width, height) = tiles::scene_resolution(&String::from_utf8_lossy(&scene));
    Ok((json!({"width": width, "height": height}), 0))
}

#[cfg(test)]
mod tests {
    use super::super::run;
    use super::super::tests_support::{args, temp_file};

    #[test]
    fn png_converts_a_tile_and_reports_its_hash() {
        let tile = temp_file(
            "png-ok.ppm",
            &silicium_raytracer::pipeline::ppm::encode(1, 1, &[9, 8, 7]),
        );
        let output = temp_file("png-ok.png", b"");
        let (payload, code) = run("png", &args(&[&tile, "--output", &output])).unwrap();
        assert_eq!(code, 0);
        assert_eq!(payload["ready"], true);
        let written = std::fs::read(&output).unwrap();
        assert!(written.starts_with(b"\x89PNG\r\n\x1a\n"));
        assert_eq!(
            payload["sha256"],
            silicium_raytracer::pipeline::sha256_hex(&written)
        );
    }

    #[test]
    fn png_rejects_a_bad_tile_without_leaving_a_file() {
        let tile = temp_file("png-bad.ppm", b"P3\n1 1\n255\n0 0 0");
        let output = temp_file("png-bad.png", b"stale");
        let (payload, code) = run("png", &args(&[&tile, "--output", &output])).unwrap();
        assert_eq!(code, 1);
        assert_eq!(payload["ready"], false);
        assert!(payload["error"]
            .as_str()
            .unwrap()
            .starts_with("unsupported_ppm_magic"));
        assert!(!std::path::Path::new(&output).exists());
    }

    #[test]
    fn resolution_reads_the_scene_or_falls_back_to_full_hd() {
        let declared = temp_file(
            "scene-a.cfg",
            b"camera : { resolution = { width = 64 height = 32 } }",
        );
        let (payload, _) = run("resolution", &args(&[&declared])).unwrap();
        assert_eq!(
            (payload["width"].as_u64(), payload["height"].as_u64()),
            (Some(64), Some(32))
        );
        let missing = temp_file("scene-b.cfg", b"camera : { fieldOfView = 60 }");
        let (payload, _) = run("resolution", &args(&[&missing])).unwrap();
        assert_eq!(
            (payload["width"].as_u64(), payload["height"].as_u64()),
            (Some(1920), Some(1080))
        );
    }
}
