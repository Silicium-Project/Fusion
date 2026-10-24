//! `silicium_raytracer`: deterministic CPU raytracer used by every compute node.
//!
//! Renders a `.cfg` scene to RGB bytes, optionally only a rectangular tile
//! ([`engine`]: several rays per pixel, free camera, Phong/diffuse/metal/
//! glass/emissive materials, point and area lights, Whitted or path-traced
//! lighting, spheres, planes, boxes, triangles, quads, meshes, transforms and
//! keyframed animation). Output must be byte-identical across machines so
//! that another peer can verify it.
//!
//! [`pipeline`] holds the rest of the tile workflow: splitting a job into tiles,
//! row-milestone commitments and their probabilistic verification, reassembly
//! and PNG export.
//!
//! The `silicium-raytracer` binary (`src/main.rs`) renders a scene (default) or
//! runs one pipeline step (`split`, `milestones`, `verify`, `reassemble`,
//! `validate`, `check`, …) and prints JSON.

pub mod check;
pub mod engine;
pub mod math;
pub mod pipeline;
pub mod render;

/// Distance under which two values are treated as equal (self-intersection guard).
pub const EPSILON: f64 = 1e-4;
