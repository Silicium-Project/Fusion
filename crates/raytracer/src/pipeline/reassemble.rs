//! Putting rendered tiles back into one image.

use super::ppm;

/// A rendered tile and where it goes.
pub struct PlacedTile<'a> {
    pub x_start: usize,
    pub y_start: usize,
    pub ppm: &'a [u8],
}

/// Reassembles tiles into one P6 image; the canvas is the smallest rectangle
/// that contains every tile, uncovered pixels stay black.
pub fn reassemble(tiles: &[PlacedTile<'_>]) -> Result<Vec<u8>, String> {
    let mut decoded = Vec::with_capacity(tiles.len());
    let (mut width, mut height) = (0usize, 0usize);
    for (index, tile) in tiles.iter().enumerate() {
        let image = ppm::parse(tile.ppm, &format!("fragment-{index}"))?;
        width = width.max(tile.x_start + image.width);
        height = height.max(tile.y_start + image.height);
        decoded.push((tile.x_start, tile.y_start, image));
    }
    let mut pixels = vec![0u8; width * height * 3];
    for (x_start, y_start, image) in decoded {
        let row_bytes = image.width * 3;
        for local_y in 0..image.height {
            let source = local_y * row_bytes;
            let target = ((y_start + local_y) * width + x_start) * 3;
            pixels[target..target + row_bytes]
                .copy_from_slice(&image.pixels[source..source + row_bytes]);
        }
    }
    Ok(ppm::encode(width, height, &pixels))
}
