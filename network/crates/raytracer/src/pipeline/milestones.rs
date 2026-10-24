//! Row milestones: a rendered tile is committed to as the SHA-256 of each block
//! of `batch_rows` rows, so a verifier only re-renders one block.

use super::{ppm, sha256_hex};
use serde::{Deserialize, Serialize};

/// Default number of rows per milestone.
pub const DEFAULT_VERIFICATION_BATCH_ROWS: usize = 20;
/// Name of the commitment scheme.
pub const STRATEGY: &str = "random-tile-row-milestone-v2";

/// One block of rows of a tile.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Milestone {
    pub index: usize,
    pub x_start: usize,
    pub x_end: usize,
    pub y_start: usize,
    pub y_end: usize,
    pub row_count: usize,
    pub pixel_sha256: String,
}

/// Commitment published by the worker that rendered a tile.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MilestoneManifest {
    pub schema_version: u32,
    pub strategy: String,
    pub image_width: usize,
    pub fragment_x_start: usize,
    pub fragment_x_end: usize,
    pub fragment_y_start: usize,
    pub fragment_y_end: usize,
    pub fragment_rows: usize,
    pub batch_rows: usize,
    pub milestone_count: usize,
    pub commitment_hash: String,
    pub milestones: Vec<Milestone>,
}

/// JSON of the milestones as Python writes it for the commitment:
/// `json.dumps(milestones, sort_keys=True, separators=(",", ":"))`.
fn commitment_material(milestones: &[Milestone]) -> String {
    let items: Vec<String> = milestones
        .iter()
        .map(|item| {
            format!(
                "{{\"index\":{},\"pixel_sha256\":\"{}\",\"row_count\":{},\"x_end\":{},\"x_start\":{},\"y_end\":{},\"y_start\":{}}}",
                item.index, item.pixel_sha256, item.row_count, item.x_end, item.x_start, item.y_end, item.y_start
            )
        })
        .collect();
    format!("[{}]", items.join(","))
}

/// Builds the milestone manifest of a rendered tile placed at
/// (`fragment_x_start`, `fragment_y_start`) in the full image.
pub fn build(
    tile_ppm: &[u8],
    fragment_y_start: usize,
    batch_rows: usize,
    fragment_x_start: usize,
) -> Result<MilestoneManifest, String> {
    let image = ppm::parse(tile_ppm, "<bytes>")?;
    let batch_rows = batch_rows.max(1);
    let stride = image.width * 3;
    let mut milestones = Vec::new();
    let mut local_y_start = 0;
    while local_y_start < image.height {
        let local_y_end = image.height.min(local_y_start + batch_rows);
        let slice = &image.pixels[local_y_start * stride..local_y_end * stride];
        milestones.push(Milestone {
            index: milestones.len(),
            x_start: fragment_x_start,
            x_end: fragment_x_start + image.width,
            y_start: fragment_y_start + local_y_start,
            y_end: fragment_y_start + local_y_end,
            row_count: local_y_end - local_y_start,
            pixel_sha256: sha256_hex(slice),
        });
        local_y_start += batch_rows;
    }
    Ok(MilestoneManifest {
        schema_version: 1,
        strategy: STRATEGY.to_string(),
        image_width: image.width,
        fragment_x_start,
        fragment_x_end: fragment_x_start + image.width,
        fragment_y_start,
        fragment_y_end: fragment_y_start + image.height,
        fragment_rows: image.height,
        batch_rows,
        milestone_count: milestones.len(),
        commitment_hash: sha256_hex(commitment_material(&milestones).as_bytes()),
        milestones,
    })
}
