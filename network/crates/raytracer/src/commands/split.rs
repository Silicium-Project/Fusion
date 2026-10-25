//! `split <scene.cfg>`: plans the tiles of a render (center-out grid).

use super::options::{absolute, read, write, Options};
use serde_json::{json, Value};
use silicium_raytracer::pipeline::{sha256_hex, tiles};
use std::path::Path;

/// `split <scene.cfg> [--fragments N] [--target-pixels N] [--max-fragments N] [--output plan.json]`.
///
/// Without `--fragments`, the tile count is estimated from the image size.
pub fn run(options: &Options) -> Result<(Value, i32), String> {
    let scene_path = options.input("scene")?;
    let scene_bytes = read(scene_path)?;
    let (width, height) = tiles::scene_resolution(&String::from_utf8_lossy(&scene_bytes));
    let target = options.number("target-pixels", tiles::DEFAULT_TARGET_PIXELS_PER_FRAGMENT)?;
    let maximum = options.number("max-fragments", tiles::DEFAULT_MAX_FRAGMENTS)?;
    let count = match options.number("fragments", 0)? {
        0 => tiles::estimate_fragment_count(width, height, target, maximum),
        requested => requested,
    };
    let scene = SceneRef {
        path: absolute(scene_path),
        sha256: sha256_hex(&scene_bytes),
    };
    let fragments: Vec<Value> = tiles::split_tiles(width, height, count)?
        .into_iter()
        .enumerate()
        .map(|(index, tile)| fragment_json(index, &tile, &scene))
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

/// The scene every fragment of the plan points to.
struct SceneRef {
    path: String,
    sha256: String,
}

fn fragment_json(index: usize, tile: &tiles::Tile, scene: &SceneRef) -> Value {
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
        "scene_path": scene.path,
        "scene_sha256": scene.sha256,
        "complexity_score": (tile.x_end - tile.x_start) * (tile.y_end - tile.y_start),
    })
}
