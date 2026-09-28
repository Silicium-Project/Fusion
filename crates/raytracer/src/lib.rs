//! `silicium_raytracer`: deterministic CPU raytracer used by every compute node.
//!
//! Renders a `.cfg` scene (spheres, planes, point lights, recursive reflections,
//! shadows, Phong highlights) to RGB bytes, optionally only a rectangular tile.
//! Output must be byte-identical across machines so that another peer can verify it.
//!
//! The `silicium-raytracer` binary (`src/main.rs`) is a thin command-line wrapper:
//! parse arguments, [`parser::parse_scene`], [`render::render`], write a PPM.

pub mod math;
pub mod parser;
pub mod render;
pub mod scene;
pub mod trace;

/// Distance under which two values are treated as equal (self-intersection guard).
pub const EPSILON: f64 = 1e-4;
/// Maximum number of reflection bounces.
pub const MAX_DEPTH: u32 = 3;
