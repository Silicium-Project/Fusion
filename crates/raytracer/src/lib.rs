//! `silicium_raytracer`: deterministic CPU raytracer used by every compute node.
//!
//! Renders a `.cfg` scene (spheres, planes, point lights, recursive reflections,
//! shadows, Phong highlights) to RGB bytes, optionally only a rectangular tile.
//! Output must be byte-identical across machines so that another peer can verify it.
//!
//! [`pipeline`] holds the rest of the tile workflow: splitting a job into tiles,
//! row-milestone commitments and their probabilistic verification, reassembly
//! and PNG export.
//!
//! The `silicium-raytracer` binary (`src/main.rs`) renders a scene (default) or
//! runs one pipeline step (`split`, `milestones`, `verify`, `reassemble`,
//! `validate`) and prints JSON.

pub mod math;
pub mod parser;
pub mod pipeline;
pub mod render;
pub mod scene;
pub mod trace;

/// Distance under which two values are treated as equal (self-intersection guard).
pub const EPSILON: f64 = 1e-4;
/// Maximum number of reflection bounces.
pub const MAX_DEPTH: u32 = 3;
