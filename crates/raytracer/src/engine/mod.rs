//! The rendering engine (version [`ENGINE_VERSION`]): reads a scene
//! ([`syntax`], [`scene`]), traces it ([`integrator`]) and reports problems
//! ([`check`]).
//!
//! Without a `render` block a scene gets one ray per pixel and the classic
//! (Whitted) lighting: Phong highlights, mirror reflections, shadows. The
//! `render` block adds several rays per pixel and path tracing. It stays
//! deterministic: the random numbers depend only on the pixel and the
//! sample ([`random::Rng`]), and the maths functions come from `libm`.

pub mod check;
pub mod geometry;
pub mod integrator;
pub mod obj;
pub mod random;
pub mod scene;
pub mod syntax;

use crate::render::{render_pixels, RenderOptions};
use std::sync::Arc;

/// Version of the engine (1 was the former Phong-only renderer). A scene
/// asking for a newer one (`render = { engine = 3 }`) is refused instead of
/// being drawn differently from the nodes that understand it.
pub const ENGINE_VERSION: u32 = 2;

/// Renders the requested tile of a scene.
///
/// Returns `(rgb_bytes, width, height, threads_used)`.
pub fn render(scene: Arc<scene::Scene>, args: &RenderOptions) -> (Vec<u8>, usize, usize, usize) {
    let (width, height) = (scene.width, scene.height);
    render_pixels(width, height, args, move |x, y| {
        integrator::pixel(&scene, x, y)
    })
}
