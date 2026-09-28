//! `compute_daemon`: local HTTP service that renders and verifies raytracer tiles.
//!
//! `POST /compute` runs `SILICIUM_RAYTRACER_BIN` and returns the SHA-256 of the
//! rendered pixels; `POST /verify` re-checks a sample of milestone hashes, the
//! sample rate decreasing with the worker's reputation. Listens on 127.0.0.1:9090.

use axum::{
    routing::post,
    Router,
    Json,
};
use serde::{Deserialize, Serialize};
use std::process::Command;
use std::{env, fs, path::Path};
use sha2::{Sha256, Digest};
use tokio::net::TcpListener;

#[derive(Deserialize)]
struct ComputeRequest {
    scene_path: String,
    output_path: String,
    y_start: Option<u32>,
    y_end: Option<u32>,
    x_start: Option<u32>,
    x_end: Option<u32>,
}

#[derive(Serialize)]
struct ComputeResponse {
    status: String,
    hash: Option<String>,
    error: Option<String>,
}

#[derive(Deserialize)]
struct Milestone {
    index: usize,
    y_start: u32,
    y_end: u32,
    pixel_sha256: String,
}

#[derive(Deserialize)]
struct Manifest {
    milestones: Option<Vec<Milestone>>,
    fragment_y_start: Option<u32>,
    milestone_count: Option<usize>,
}

#[derive(Deserialize)]
struct VerifyRequest {
    ppm_path: String,
    manifest: Manifest,
    seed: String,
    reputation: Option<f64>,
}

#[derive(Serialize, Clone)]
struct FailedMilestone {
    index: usize,
    expected: String,
    actual: String,
}

#[derive(Serialize)]
struct VerifyResponse {
    verified: bool,
    escalated_to_full: bool,
    sample_rate: f64,
    sampled_count: usize,
    total_milestones: usize,
    failed_milestones: Vec<FailedMilestone>,
    reason: String,
}

fn calculate_sampling_rate(reputation_score: f64) -> f64 {
    let rep = reputation_score.max(0.0);
    if rep >= 100.0 {
        return 0.2;
    }
    let rate = 1.0 - (rep / 100.0) * (1.0 - 0.2);
    rate.clamp(0.2, 1.0)
}

fn parse_ppm_pixels(data: &[u8]) -> Result<(u32, u32, &[u8]), String> {
    let mut idx = 0;

    fn token<'a>(data: &'a [u8], idx: &mut usize) -> Result<&'a [u8], String> {
        loop {
            while *idx < data.len() && (data[*idx] as char).is_whitespace() {
                *idx += 1;
            }
            if *idx < data.len() && data[*idx] == b'#' {
                while *idx < data.len() && data[*idx] != b'\n' && data[*idx] != b'\r' {
                    *idx += 1;
                }
                continue;
            }
            let start = *idx;
            while *idx < data.len() && !(data[*idx] as char).is_whitespace() {
                *idx += 1;
            }
            if start == *idx {
                return Err("Unexpected EOF".to_string());
            }
            return Ok(&data[start..*idx]);
        }
    }

    let magic = token(data, &mut idx)?;
    if magic != b"P6" {
        return Err("Unsupported magic".to_string());
    }

    let width_str = std::str::from_utf8(token(data, &mut idx)?).map_err(|_| "Invalid width format")?;
    let width: u32 = width_str.parse().map_err(|_| "Invalid width")?;

    let height_str = std::str::from_utf8(token(data, &mut idx)?).map_err(|_| "Invalid height format")?;
    let height: u32 = height_str.parse().map_err(|_| "Invalid height")?;

    let max_val_str = std::str::from_utf8(token(data, &mut idx)?).map_err(|_| "Invalid max_val format")?;
    let max_val: u32 = max_val_str.parse().map_err(|_| "Invalid max_val")?;
    if max_val != 255 {
        return Err("Unsupported max_val".to_string());
    }

    if idx < data.len() {
        if data[idx] == b'\r' && idx + 1 < data.len() && data[idx+1] == b'\n' {
            idx += 2;
        } else {
            idx += 1;
        }
    }

    let pixels = &data[idx..];
    let expected = (width * height * 3) as usize;
    if pixels.len() != expected {
        return Err(format!("Invalid payload size: expected {}, actual {}", expected, pixels.len()));
    }

    Ok((width, height, pixels))
}

fn ppm_pixel_sha256(data: &[u8]) -> Result<String, String> {
    let (_, _, pixels) = parse_ppm_pixels(data)?;
    let mut hasher = Sha256::new();
    hasher.update(pixels);
    Ok(hex::encode(hasher.finalize()))
}

async fn handle_compute(Json(req): Json<ComputeRequest>) -> Json<ComputeResponse> {
    let binary = match env::var("SILICIUM_RAYTRACER_BIN") {
        Ok(val) => val,
        Err(_) => return Json(ComputeResponse {
            status: "error".to_string(),
            hash: None,
            error: Some("SILICIUM_RAYTRACER_BIN not set".to_string()),
        }),
    };

    let mut cmd = Command::new(&binary);
    cmd.arg(&req.scene_path)
       .arg("--output")
       .arg(&req.output_path);

    if let Some(y_s) = req.y_start { cmd.arg("--y-start").arg(y_s.to_string()); }
    if let Some(y_e) = req.y_end { cmd.arg("--y-end").arg(y_e.to_string()); }
    if let Some(x_s) = req.x_start { cmd.arg("--x-start").arg(x_s.to_string()); }
    if let Some(x_e) = req.x_end { cmd.arg("--x-end").arg(x_e.to_string()); }

    let output = cmd.output();
    match output {
        Ok(out) => {
            if !out.status.success() {
                return Json(ComputeResponse {
                    status: "error".to_string(),
                    hash: None,
                    error: Some(String::from_utf8_lossy(&out.stderr).to_string()),
                });
            }
        },
        Err(e) => {
            return Json(ComputeResponse {
                status: "error".to_string(),
                hash: None,
                error: Some(e.to_string()),
            });
        }
    }

    let ppm_bytes = match fs::read(Path::new(&req.output_path)) {
        Ok(b) => b,
        Err(e) => return Json(ComputeResponse {
            status: "error".to_string(),
            hash: None,
            error: Some(e.to_string()),
        }),
    };

    match ppm_pixel_sha256(&ppm_bytes) {
        Ok(hash_val) => Json(ComputeResponse {
            status: "success".to_string(),
            hash: Some(hash_val),
            error: None,
        }),
        Err(e) => Json(ComputeResponse {
            status: "error".to_string(),
            hash: None,
            error: Some(e),
        })
    }
}

async fn handle_verify(Json(req): Json<VerifyRequest>) -> Json<VerifyResponse> {
    let ppm_bytes = match fs::read(&req.ppm_path) {
        Ok(b) => b,
        Err(e) => return Json(VerifyResponse {
            verified: false,
            escalated_to_full: true,
            sample_rate: 0.0,
            sampled_count: 0,
            total_milestones: 0,
            failed_milestones: vec![],
            reason: format!("Failed to read ppm: {}", e),
        })
    };

    let (width, _, pixels) = match parse_ppm_pixels(&ppm_bytes) {
        Ok(r) => r,
        Err(e) => return Json(VerifyResponse {
            verified: false,
            escalated_to_full: true,
            sample_rate: 0.0,
            sampled_count: 0,
            total_milestones: 0,
            failed_milestones: vec![],
            reason: format!("Invalid ppm: {}", e),
        })
    };

    let row_stride = (width * 3) as usize;
    let fragment_y_start = req.manifest.fragment_y_start.unwrap_or(0);
    let reputation = req.reputation.unwrap_or(50.0);
    let sample_rate = calculate_sampling_rate(reputation);

    let milestones = req.manifest.milestones.unwrap_or_default();
    let total_milestones = milestones.len();
    if total_milestones == 0 {
        return Json(VerifyResponse {
            verified: true,
            escalated_to_full: false,
            sample_rate: 0.0,
            sampled_count: 0,
            total_milestones: 0,
            failed_milestones: vec![],
            reason: "".to_string(),
        });
    }

    let target_count = ((total_milestones as f64) * sample_rate).ceil() as usize;
    let target_count = target_count.max(1);

    let mut scored = Vec::new();
    for ms in milestones {
        let mut hasher = Sha256::new();
        hasher.update(format!("{}:{}", req.seed, ms.index));
        let score = hex::encode(hasher.finalize());
        scored.push((score, ms));
    }
    scored.sort_by(|a, b| a.0.cmp(&b.0));

    let sampled: Vec<_> = scored.into_iter().take(target_count).map(|x| x.1).collect();

    let mut failed_milestones = Vec::new();
    for ms in &sampled {
        let local_y_start = (ms.y_start.saturating_sub(fragment_y_start)) as usize;
        let local_y_end = (ms.y_end.saturating_sub(fragment_y_start)) as usize;
        
        let start_idx = local_y_start * row_stride;
        let end_idx = local_y_end * row_stride;
        
        if end_idx > pixels.len() {
            failed_milestones.push(FailedMilestone {
                index: ms.index,
                expected: ms.pixel_sha256.clone(),
                actual: "out_of_bounds".to_string(),
            });
            continue;
        }

        let slice = &pixels[start_idx..end_idx];
        let mut hasher = Sha256::new();
        hasher.update(slice);
        let actual = hex::encode(hasher.finalize());
        
        if actual != ms.pixel_sha256 {
            failed_milestones.push(FailedMilestone {
                index: ms.index,
                expected: ms.pixel_sha256.clone(),
                actual,
            });
        }
    }

    if !failed_milestones.is_empty() {
        let len = failed_milestones.len();
        return Json(VerifyResponse {
            verified: false,
            escalated_to_full: true,
            sample_rate,
            sampled_count: sampled.len(),
            total_milestones: req.manifest.milestone_count.unwrap_or(total_milestones),
            failed_milestones,
            reason: format!("probabilistic_milestone_verification_failed:{}_mismatches", len),
        });
    }

    Json(VerifyResponse {
        verified: true,
        escalated_to_full: false,
        sample_rate,
        sampled_count: sampled.len(),
        total_milestones: req.manifest.milestone_count.unwrap_or(total_milestones),
        failed_milestones: vec![],
        reason: "".to_string(),
    })
}

#[tokio::main]
async fn main() {
    let app = Router::new()
        .route("/compute", post(handle_compute))
        .route("/verify", post(handle_verify));

    let listener = TcpListener::bind("127.0.0.1:9090").await.unwrap();
    println!("Compute Daemon (Rust) running on port 9090...");
    axum::serve(listener, app).await.unwrap();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_calculate_sampling_rate() {
        assert_eq!(calculate_sampling_rate(150.0), 0.2);
        assert_eq!(calculate_sampling_rate(100.0), 0.2);
        assert_eq!(calculate_sampling_rate(50.0), 0.6);
        assert_eq!(calculate_sampling_rate(0.0), 1.0);
        assert_eq!(calculate_sampling_rate(-50.0), 1.0);
    }

    #[test]
    fn test_parse_ppm_pixels_valid() {
        let ppm = b"P6\n2 2\n255\nRGBRGBRGBRGB";
        let (width, height, pixels) = parse_ppm_pixels(ppm).unwrap();
        assert_eq!(width, 2);
        assert_eq!(height, 2);
        assert_eq!(pixels.len(), 12);
        assert_eq!(pixels, b"RGBRGBRGBRGB");
    }

    #[test]
    fn test_parse_ppm_pixels_with_comments() {
        let ppm = b"P6\n# A comment\n2 2\n255\nRGBRGBRGBRGB";
        let (width, height, pixels) = parse_ppm_pixels(ppm).unwrap();
        assert_eq!(width, 2);
        assert_eq!(height, 2);
        assert_eq!(pixels.len(), 12);
    }

    #[test]
    fn test_parse_ppm_pixels_invalid() {
        assert!(parse_ppm_pixels(b"P5\n2 2\n255\n1234").is_err());
        assert!(parse_ppm_pixels(b"P6\n2 2\n256\n1234").is_err());
        assert!(parse_ppm_pixels(b"P6\n2 2\n255\nRGB").is_err()); // Too short
    }
}
