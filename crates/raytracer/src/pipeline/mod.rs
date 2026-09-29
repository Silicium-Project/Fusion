//! Tile pipeline around the renderer: how a job is split into tiles, how a
//! rendered tile is committed to (row milestones) and checked by another peer,
//! and how tiles are put back together.
//!
//! Every function is a port of `workloads/raytracer/raytracer_workload.py` and
//! must stay byte-for-byte compatible with it: the fixtures in
//! `tests/fixtures/python_parity.json` are produced by the Python code
//! (`tools/dev/quality/raytracer_parity_fixtures.py`).

pub mod milestones;
pub mod png;
pub mod ppm;
pub mod reassemble;
pub mod sampling;
pub mod tiles;

use sha2::{Digest, Sha256};

/// Lower-case hex SHA-256.
pub fn sha256_hex(data: &[u8]) -> String {
    let digest = Sha256::digest(data);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// Python's `round(value, digits)` (round half to even on the exact value).
pub(crate) fn py_round(value: f64, digits: usize) -> f64 {
    format!("{value:.digits$}").parse().unwrap_or(value)
}
