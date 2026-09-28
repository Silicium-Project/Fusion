//! Recursive ray tracing: nearest hit, shadows, diffuse + Phong lighting,
//! reflections up to [`crate::MAX_DEPTH`] bounces.

use crate::{
    math::{Ray, Vec3},
    scene::{Hit, Scene},
    EPSILON, MAX_DEPTH,
};

fn nearest_hit(scene: &Scene, ray: Ray) -> Option<Hit> {
    scene
        .primitives
        .iter()
        .filter_map(|primitive| primitive.intersect(ray))
        .min_by(|left, right| left.distance.total_cmp(&right.distance))
}

fn background(direction: Vec3) -> Vec3 {
    let amount = (direction.z + 1.0) * 0.5;
    Vec3::new(0.04, 0.07, 0.13) * (1.0 - amount) + Vec3::new(0.34, 0.55, 0.9) * amount
}

/// Colour seen along `ray` (each channel in `0.0..=1.0`).
pub fn trace(scene: &Scene, ray: Ray, depth: u32) -> Vec3 {
    let Some(hit) = nearest_hit(scene, ray) else {
        return background(ray.direction);
    };
    let mut diffuse_light = Vec3::new(0.09, 0.09, 0.11);
    let mut specular_light = Vec3::default();
    let view = -ray.direction;
    for light in &scene.lights {
        let displacement = light.position - hit.point;
        let distance_squared = displacement.dot(displacement).max(1.0);
        let distance = distance_squared.sqrt();
        let light_direction = displacement / distance;
        let shadow_ray = Ray {
            origin: hit.point + hit.normal * (EPSILON * 4.0),
            direction: light_direction,
        };
        if nearest_hit(scene, shadow_ray)
            .map(|shadow| shadow.distance < distance - EPSILON)
            .unwrap_or(false)
        {
            continue;
        }
        let attenuation = (light.intensity / distance_squared).min(1.5);
        let lambert = hit.normal.dot(light_direction).max(0.0);
        diffuse_light = diffuse_light + light.color * (lambert * attenuation);
        let reflected_light = (-light_direction).reflect(hit.normal).normalized();
        let highlight = reflected_light
            .dot(view)
            .max(0.0)
            .powf(hit.material.shininess)
            * hit.material.specular
            * attenuation;
        specular_light = specular_light + light.color * highlight;
    }
    let local = hit.material.color.hadamard(diffuse_light) + specular_light;
    if depth >= MAX_DEPTH || hit.material.reflectivity <= 0.0 {
        return local.clamp();
    }
    let reflected = trace(
        scene,
        Ray {
            origin: hit.point + hit.normal * (EPSILON * 4.0),
            direction: ray.direction.reflect(hit.normal).normalized(),
        },
        depth + 1,
    );
    (local * (1.0 - hit.material.reflectivity) + reflected * hit.material.reflectivity).clamp()
}
