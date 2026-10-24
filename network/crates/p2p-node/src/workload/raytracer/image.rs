//! Checking a downloaded tile against its milestone commitment: every
//! committed block of rows must hash to its `pixel_sha256` at the tile's
//! place in the image. Verifiers re-render milestones, not the uploaded
//! file, so without this check a worker could commit honest milestones and
//! upload another image.

use silicium_node_core::taskbook::MilestoneSample;
use silicium_raytracer::pipeline::{ppm, sha256_hex};

/// True when every milestone's block of `image` (a P6 PPM whose top-left
/// pixel sits at `origin` in the full image) hashes to its commitment.
pub(crate) fn image_matches_milestones(
    image: &[u8],
    milestones: &[MilestoneSample],
    origin: (u32, u32),
) -> bool {
    let Ok(image) = ppm::parse(image, "result") else {
        return false;
    };
    !milestones.is_empty()
        && milestones.iter().all(|milestone| {
            block_hash(&image, milestone, origin).as_deref() == Some(&milestone.pixel_sha256)
        })
}

/// SHA-256 of a milestone's block of rows, or `None` when it falls outside
/// the image.
fn block_hash(image: &ppm::Ppm, milestone: &MilestoneSample, origin: (u32, u32)) -> Option<String> {
    let to_local = |value: u32, start: u32| value.checked_sub(start).map(|v| v as usize);
    let x_start = to_local(milestone.x_start, origin.0)?;
    let x_end = to_local(milestone.x_end, origin.0)?;
    let y_start = to_local(milestone.y_start, origin.1)?;
    let y_end = to_local(milestone.y_end, origin.1)?;
    if x_start >= x_end || y_start >= y_end || x_end > image.width || y_end > image.height {
        return None;
    }
    let stride = image.width * 3;
    let mut block = Vec::with_capacity((x_end - x_start) * 3 * (y_end - y_start));
    for row in y_start..y_end {
        let offset = row * stride;
        block.extend_from_slice(&image.pixels[offset + x_start * 3..offset + x_end * 3]);
    }
    Some(sha256_hex(&block))
}

#[cfg(test)]
mod tests {
    use super::*;
    use silicium_raytracer::pipeline::milestones;

    fn pattern(width: usize, height: usize) -> Vec<u8> {
        let pixels: Vec<u8> = (0..width * height * 3)
            .map(|i| (i * 31 % 256) as u8)
            .collect();
        ppm::encode(width, height, &pixels)
    }

    fn samples(image: &[u8], y: usize, x: usize) -> Vec<MilestoneSample> {
        milestones::build(image, y, 4, x)
            .unwrap()
            .milestones
            .into_iter()
            .map(|m| MilestoneSample {
                index: m.index as u32,
                x_start: m.x_start as u32,
                x_end: m.x_end as u32,
                y_start: m.y_start as u32,
                y_end: m.y_end as u32,
                pixel_sha256: m.pixel_sha256,
            })
            .collect()
    }

    #[test]
    fn the_committed_image_matches_and_another_does_not() {
        let image = pattern(6, 10);
        let committed = samples(&image, 0, 0);
        assert!(image_matches_milestones(&image, &committed, (0, 0)));
        let mut other = image.clone();
        let last = other.len() - 1;
        other[last] ^= 0xff;
        assert!(!image_matches_milestones(&other, &committed, (0, 0)));
        assert!(!image_matches_milestones(&image, &[], (0, 0)));
        assert!(!image_matches_milestones(b"not a ppm", &committed, (0, 0)));
    }

    #[test]
    fn a_tile_is_checked_at_its_place_in_the_image() {
        let tile = pattern(3, 5);
        let committed = samples(&tile, 20, 7);
        assert!(image_matches_milestones(&tile, &committed, (7, 20)));
        assert!(!image_matches_milestones(&tile, &committed, (0, 0)));
    }
}
