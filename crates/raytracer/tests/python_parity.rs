//! The Rust tile pipeline must give exactly the results of the legacy Python
//! one. `fixtures/python_parity.json` is produced by
//! `tools/dev/quality/raytracer_parity_fixtures.py`.

use serde_json::Value;
use silicium_raytracer::pipeline::{milestones, ppm, reassemble, sampling, sha256_hex, tiles};

fn fixtures() -> Value {
    let text = include_str!("fixtures/python_parity.json");
    serde_json::from_str(text).expect("valid fixture JSON")
}

/// Same image as `pattern_ppm` in the fixture generator.
fn pattern_ppm(width: usize, height: usize, seed: usize) -> Vec<u8> {
    let pixels: Vec<u8> = (0..width * height * 3)
        .map(|index| ((index * 31 + seed * 7) % 256) as u8)
        .collect();
    ppm::encode(width, height, &pixels)
}

fn as_usize(value: &Value) -> usize {
    value.as_u64().expect("unsigned integer") as usize
}

#[test]
fn split_tiles_matches_python() {
    let data = fixtures();
    for case in data["split"].as_array().unwrap() {
        let got = tiles::split_tiles(
            as_usize(&case["width"]),
            as_usize(&case["height"]),
            as_usize(&case["count"]),
        )
        .unwrap();
        let expected: Vec<tiles::Tile> = serde_json::from_value(case["tiles"].clone()).unwrap();
        assert_eq!(got, expected, "split {case:?}");
    }
}

#[test]
fn scene_resolution_and_fragment_estimate_match_python() {
    let data = fixtures();
    for case in data["resolution"].as_array().unwrap() {
        let (width, height) = tiles::scene_resolution(case["scene"].as_str().unwrap());
        assert_eq!(
            vec![width, height],
            vec![
                as_usize(&case["resolution"][0]),
                as_usize(&case["resolution"][1])
            ],
            "{case:?}"
        );
    }
    for case in data["estimate"].as_array().unwrap() {
        let (width, height) = tiles::scene_resolution(case["scene"].as_str().unwrap());
        let got = tiles::estimate_fragment_count(
            width,
            height,
            as_usize(&case["target"]),
            as_usize(&case["max"]),
        );
        assert_eq!(got, as_usize(&case["count"]), "{case:?}");
    }
}

#[test]
fn milestones_and_commitment_match_python() {
    let data = fixtures();
    for case in data["milestones"].as_array().unwrap() {
        let image = pattern_ppm(
            as_usize(&case["width"]),
            as_usize(&case["height"]),
            as_usize(&case["seed"]),
        );
        assert_eq!(
            ppm::pixel_sha256(&image).unwrap(),
            case["pixel_sha256"].as_str().unwrap()
        );
        let manifest = milestones::build(
            &image,
            as_usize(&case["y_start"]),
            as_usize(&case["batch_rows"]),
            as_usize(&case["x_start"]),
        )
        .unwrap();
        assert_eq!(
            serde_json::to_value(&manifest).unwrap(),
            case["manifest"],
            "{case:?}"
        );
    }
}

#[test]
fn sampling_selection_and_detection_match_python() {
    let data = fixtures();
    for case in data["sampling_rates"].as_array().unwrap() {
        let rate = sampling::sampling_rate(case["reputation"].as_f64().unwrap());
        assert_eq!(rate, case["rate"].as_f64().unwrap(), "{case:?}");
    }
    let manifest: sampling::SampledManifest =
        serde_json::from_value(data["selection_manifest"].clone()).unwrap();
    let indexes: Vec<usize> = manifest.milestones.iter().map(|item| item.index).collect();
    for case in data["selection"].as_array().unwrap() {
        let got = sampling::select(
            &indexes,
            case["seed"].as_str().unwrap(),
            case["rate"].as_f64().unwrap(),
        );
        let expected: Vec<usize> = serde_json::from_value(case["indices"].clone()).unwrap();
        assert_eq!(got, expected, "{case:?}");
    }
    for case in data["detection"].as_array().unwrap() {
        let got = sampling::detection_probability(
            as_usize(&case["total"]),
            as_usize(&case["tampered"]),
            as_usize(&case["sampled"]),
        );
        assert_eq!(got, case["probability"].as_f64().unwrap(), "{case:?}");
    }
}

#[test]
fn probabilistic_verification_matches_python() {
    let data = fixtures();
    let manifest: sampling::SampledManifest =
        serde_json::from_value(data["selection_manifest"].clone()).unwrap();
    let good = pattern_ppm(6, 50, 9);
    let mut tampered = good.clone();
    *tampered.last_mut().unwrap() ^= 0xFF;
    for case in data["verify"].as_array().unwrap() {
        let image = if case["image"] == "good" {
            &good
        } else {
            &tampered
        };
        let got = sampling::verify(
            image,
            &manifest,
            case["seed"].as_str().unwrap(),
            case["reputation"].as_f64().unwrap(),
        )
        .unwrap();
        assert_eq!(
            serde_json::to_value(&got).unwrap(),
            case["result"],
            "{case:?}"
        );
    }
}

#[test]
fn reassembly_matches_python() {
    let data = fixtures();
    let case = &data["reassembly"];
    let images: Vec<(usize, usize, Vec<u8>)> = case["fragments"]
        .as_array()
        .unwrap()
        .iter()
        .map(|item| {
            (
                as_usize(&item["x"]),
                as_usize(&item["y"]),
                pattern_ppm(
                    as_usize(&item["width"]),
                    as_usize(&item["height"]),
                    as_usize(&item["seed"]),
                ),
            )
        })
        .collect();
    let placed: Vec<reassemble::PlacedTile<'_>> = images
        .iter()
        .map(|(x, y, image)| reassemble::PlacedTile {
            x_start: *x,
            y_start: *y,
            ppm: image,
        })
        .collect();
    let output = reassemble::reassemble(&placed).unwrap();
    assert_eq!(sha256_hex(&output), case["sha256"].as_str().unwrap());
}

#[test]
fn ppm_parsing_errors_match_python() {
    let data = fixtures();
    for case in data["parse"].as_array().unwrap() {
        let bytes: Vec<u8> = serde_json::from_value(case["data"].clone()).unwrap();
        let label = case["label"].as_str().unwrap();
        match (ppm::parse(&bytes, label), case.get("error")) {
            (Err(error), Some(expected)) => assert_eq!(error, expected.as_str().unwrap()),
            (Ok(image), None) => {
                assert_eq!(image.width, as_usize(&case["ok"][0]));
                assert_eq!(image.height, as_usize(&case["ok"][1]));
                assert_eq!(sha256_hex(&image.pixels), case["ok"][2].as_str().unwrap());
            }
            (got, expected) => panic!("{label}: got {got:?}, expected {expected:?}"),
        }
    }
}

#[test]
fn png_round_trips_the_pixels() {
    let image = pattern_ppm(5, 4, 3);
    let decoded = ppm::parse(&image, "t").unwrap();
    let png = silicium_raytracer::pipeline::png::encode_rgb(5, 4, &decoded.pixels).unwrap();
    assert!(png.starts_with(b"\x89PNG\r\n\x1a\n"));
    // IDAT holds zlib(filter byte + row) for each row.
    let idat = png.windows(4).position(|window| window == b"IDAT").unwrap();
    let length = u32::from_be_bytes(png[idat - 4..idat].try_into().unwrap()) as usize;
    let mut raw = Vec::new();
    use std::io::Read;
    flate2::read::ZlibDecoder::new(&png[idat + 4..idat + 4 + length])
        .read_to_end(&mut raw)
        .unwrap();
    let rows: Vec<u8> = raw.chunks(16).flat_map(|row| row[1..].to_vec()).collect();
    assert_eq!(rows, decoded.pixels);
}
