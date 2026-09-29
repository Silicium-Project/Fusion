//! Splitting an image into rectangular tiles, ordered from the centre outwards.

use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::{HashSet, VecDeque};

/// Default target size of a tile, in pixels.
pub const DEFAULT_TARGET_PIXELS_PER_FRAGMENT: usize = 120_000;
/// Default maximum number of tiles per job.
pub const DEFAULT_MAX_FRAGMENTS: usize = 32;

/// One tile of the image (`*_end` exclusive).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Tile {
    pub tile_row: usize,
    pub tile_column: usize,
    pub x_start: usize,
    pub x_end: usize,
    pub y_start: usize,
    pub y_end: usize,
}

/// Image size declared by a scene file (`resolution = { width = W height = H }`),
/// 1920x1080 when absent — same rule as the Python splitter.
pub fn scene_resolution(scene_text: &str) -> (usize, usize) {
    let pattern =
        Regex::new(r"(?i)resolution\s*=\s*\{[^}]*width\s*=\s*(\d+)[^}]*height\s*=\s*(\d+)")
            .expect("valid resolution pattern");
    pattern
        .captures(scene_text)
        .and_then(|captures| {
            let width = captures[1].parse::<usize>().ok()?;
            let height = captures[2].parse::<usize>().ok()?;
            Some((width.max(1), height.max(1)))
        })
        .unwrap_or((1920, 1080))
}

/// Number of tiles for an image: about `target_pixels` each, at most
/// `max_fragments`, never more than one per row.
pub fn estimate_fragment_count(
    width: usize,
    height: usize,
    target_pixels: usize,
    max_fragments: usize,
) -> usize {
    let pixels = (width * height) as f64;
    let fragments = ((pixels / target_pixels.max(1) as f64).ceil() as usize).max(1);
    fragments.min(max_fragments.max(1)).min(height).max(1)
}

fn round_div(numerator: usize, denominator: usize) -> usize {
    (numerator as f64 / denominator as f64).round_ties_even() as usize
}

/// Covers the image with exactly `fragment_count` tiles (rows may differ by one
/// column) and orders them breadth-first over edge-sharing neighbours, starting
/// from the tile closest to the centre.
pub fn split_tiles(
    width: usize,
    height: usize,
    fragment_count: usize,
) -> Result<Vec<Tile>, String> {
    let fragment_count = fragment_count.max(1).min(width * height);
    let ideal_rows = ((fragment_count * height) as f64 / width as f64)
        .sqrt()
        .round_ties_even() as usize;
    let row_count = fragment_count
        .div_ceil(width)
        .max(height.min(fragment_count).min(ideal_rows.max(1)));
    let base_columns = fragment_count / row_count;
    let extra_columns = fragment_count % row_count;

    let mut tiles: Vec<Tile> = Vec::new();
    let mut rows: Vec<Vec<usize>> = Vec::new();
    for row in 0..row_count {
        let column_count = base_columns + usize::from(row < extra_columns);
        let y_start = round_div(row * height, row_count);
        let y_end = round_div((row + 1) * height, row_count);
        let mut row_tiles = Vec::new();
        for column in 0..column_count {
            let x_start = round_div(column * width, column_count);
            let x_end = round_div((column + 1) * width, column_count);
            if x_end <= x_start || y_end <= y_start {
                continue;
            }
            row_tiles.push(tiles.len());
            tiles.push(Tile {
                tile_row: row,
                tile_column: column,
                x_start,
                x_end,
                y_start,
                y_end,
            });
        }
        rows.push(row_tiles);
    }

    let center_x = width as f64 / 2.0;
    let center_y = height as f64 / 2.0;
    let mut start = 0;
    let mut best_distance = f64::INFINITY;
    for (index, tile) in tiles.iter().enumerate() {
        let tile_x = (tile.x_start + tile.x_end) as f64 / 2.0;
        let tile_y = (tile.y_start + tile.y_end) as f64 / 2.0;
        let distance = (tile_x - center_x).powi(2) + (tile_y - center_y).powi(2);
        if distance < best_distance {
            start = index;
            best_distance = distance;
        }
    }

    let mut neighbours: Vec<Vec<usize>> = vec![Vec::new(); tiles.len()];
    for (row, row_tiles) in rows.iter().enumerate() {
        for (position, &tile_index) in row_tiles.iter().enumerate() {
            if let Some(&right) = row_tiles.get(position + 1) {
                neighbours[tile_index].push(right);
                neighbours[right].push(tile_index);
            }
            for adjacent_row in [row.checked_sub(1), Some(row + 1)].into_iter().flatten() {
                let Some(candidates) = rows.get(adjacent_row) else {
                    continue;
                };
                let tile = &tiles[tile_index];
                for &candidate in candidates {
                    let other = &tiles[candidate];
                    if tile.x_end.min(other.x_end) > tile.x_start.max(other.x_start) {
                        neighbours[tile_index].push(candidate);
                    }
                }
            }
        }
    }

    let mut ordered = Vec::with_capacity(tiles.len());
    let mut pending = VecDeque::from([start]);
    let mut visited = HashSet::from([start]);
    while let Some(index) = pending.pop_front() {
        ordered.push(tiles[index].clone());
        for &neighbour in &neighbours[index] {
            if visited.insert(neighbour) {
                pending.push_back(neighbour);
            }
        }
    }
    if ordered.len() != tiles.len() {
        return Err("raytracer_tile_graph_disconnected".to_string());
    }
    Ok(ordered)
}
