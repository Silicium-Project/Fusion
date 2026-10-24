//! Colour of a pixel: several camera rays per pixel, each traced with the
//! Whitted model (Phong highlights, mirror reflections, shadows, plus glass,
//! metal and area lights) or with Monte-Carlo path tracing, then averaged,
//! tone-mapped and gamma-corrected (square root).

use super::{
    geometry::Shape,
    random::{pow, Rng},
    scene::{Material, MaterialKind, Mode, Scene, Tonemap, LIGHT_UNIT},
};
use crate::{math::Vec3, EPSILON};
use std::f64::consts::PI;

/// Hit seen from a ray.
#[derive(Clone, Copy, Debug)]
struct Hit {
    distance: f64,
    point: Vec3,
    /// Facing the incoming ray.
    normal: Vec3,
    /// True when the ray comes from the outside of the surface.
    front_face: bool,
    shape: usize,
}

fn nearest(scene: &Scene, origin: Vec3, direction: Vec3, limit: f64) -> Option<Hit> {
    let mut best = scene.bvh.intersect(&scene.shapes, origin, direction, limit);
    for &plane in &scene.planes {
        if let Some((distance, normal)) = scene.shapes[plane].intersect(origin, direction) {
            if distance < best.map_or(limit, |hit| hit.0) {
                best = Some((distance, normal, plane));
            }
        }
    }
    best.map(|(distance, outward, shape)| {
        let front_face = outward.dot(direction) < 0.0;
        Hit {
            distance,
            point: origin + direction * distance,
            normal: if front_face { outward } else { -outward },
            front_face,
            shape,
        }
    })
}

fn material_of<'a>(scene: &'a Scene, hit: &Hit) -> &'a Material {
    &scene.materials[scene.shape_material[hit.shape]]
}

/// Light let through between `origin` and `distance` along `direction`:
/// black behind an opaque object, tinted behind glass. `light` (the shape
/// of the light being sampled) never hides itself.
fn transmittance(
    scene: &Scene,
    mut origin: Vec3,
    direction: Vec3,
    mut distance: f64,
    light: Option<usize>,
) -> Vec3 {
    let mut through = Vec3::new(1.0, 1.0, 1.0);
    for _ in 0..8 {
        let Some(hit) = nearest(scene, origin, direction, distance - EPSILON) else {
            return through;
        };
        if Some(hit.shape) == light {
            return through;
        }
        let material = material_of(scene, &hit);
        if material.kind != MaterialKind::Glass {
            return Vec3::default();
        }
        through = through.hadamard(material.color) * 0.92;
        origin = hit.point + direction * (EPSILON * 4.0);
        distance -= hit.distance;
    }
    Vec3::default()
}

fn background(scene: &Scene, direction: Vec3) -> Vec3 {
    let amount = (direction.z + 1.0) * 0.5;
    (Vec3::new(0.04, 0.07, 0.13) * (1.0 - amount) + Vec3::new(0.34, 0.55, 0.9) * amount)
        * scene.settings.sky
}

fn refract(direction: Vec3, normal: Vec3, eta: f64) -> Option<Vec3> {
    let cos_i = (-direction).dot(normal).min(1.0);
    let k = 1.0 - eta * eta * (1.0 - cos_i * cos_i);
    (k >= 0.0).then(|| (direction * eta + normal * (eta * cos_i - k.sqrt())).normalized())
}

/// Schlick's approximation of the Fresnel reflectance.
fn fresnel(cos_i: f64, eta: f64) -> f64 {
    let ratio = (1.0 - eta) / (1.0 + eta);
    let r0 = ratio * ratio;
    let m = 1.0 - cos_i;
    r0 + (1.0 - r0) * (m * m * m * m * m)
}

/// Mirror direction blurred by `roughness` (0 = perfect mirror).
fn glossy(reflected: Vec3, roughness: f64, rng: &mut Rng) -> Vec3 {
    if roughness <= 0.0 {
        return reflected;
    }
    (reflected + rng.in_sphere() * roughness).normalized()
}

/// A light seen from a shaded point (Whitted mode): direction, distance,
/// intensity and colour.
fn whitted_lights(
    scene: &Scene,
    point: Vec3,
    rng: &mut Rng,
) -> Vec<(Vec3, f64, f64, Vec3, Option<usize>)> {
    let mut lights: Vec<(Vec3, f64, f64, Vec3, Option<usize>)> = scene
        .points
        .iter()
        .map(|light| {
            let displacement = light.position - point;
            (
                displacement,
                displacement.dot(displacement),
                light.intensity,
                light.color,
                None,
            )
        })
        .collect();
    for emitter in &scene.emitters {
        let (Some(intensity), Shape::Sphere { center, radius }) =
            (emitter.intensity, &scene.shapes[emitter.shape])
        else {
            continue;
        };
        // A random point of the half of the light facing the point: soft
        // shadows over the samples.
        let mut offset = rng.on_sphere();
        if offset.dot(point - *center) < 0.0 {
            offset = -offset;
        }
        let displacement = *center + offset * *radius - point;
        lights.push((
            displacement,
            (*center - point).dot(*center - point),
            intensity,
            emitter.color,
            Some(emitter.shape),
        ));
    }
    lights
}

/// Classic (Phong) lighting of a point: diffuse light and highlights.
fn phong_light(
    scene: &Scene,
    hit: &Hit,
    view: Vec3,
    shininess: f64,
    specular: f64,
    rng: &mut Rng,
) -> (Vec3, Vec3) {
    let mut diffuse = Vec3::new(0.09, 0.09, 0.11);
    let mut highlight = Vec3::default();
    for (displacement, centre_distance_squared, intensity, color, shape) in
        whitted_lights(scene, hit.point, rng)
    {
        let direction = displacement / displacement.length().max(EPSILON);
        let through = transmittance(
            scene,
            hit.point + hit.normal * (EPSILON * 4.0),
            direction,
            displacement.length(),
            shape,
        );
        if through.max_component() <= 0.0 {
            continue;
        }
        let attenuation = (intensity / centre_distance_squared.max(1.0)).min(1.5);
        let lambert = hit.normal.dot(direction).max(0.0);
        diffuse = diffuse + color.hadamard(through) * (lambert * attenuation);
        let reflected = (-direction).reflect(hit.normal).normalized();
        let shine = pow(reflected.dot(view).max(0.0), shininess) * specular * attenuation;
        highlight = highlight + color.hadamard(through) * shine;
    }
    (diffuse, highlight)
}

fn whitted(scene: &Scene, origin: Vec3, direction: Vec3, depth: u32, rng: &mut Rng) -> Vec3 {
    let Some(hit) = nearest(scene, origin, direction, f64::INFINITY) else {
        return background(scene, direction);
    };
    let material = *material_of(scene, &hit);
    let view = -direction;
    let outside = hit.point + hit.normal * (EPSILON * 4.0);
    let inside = hit.point - hit.normal * (EPSILON * 4.0);
    let deeper = depth < scene.settings.bounces;
    match material.kind {
        MaterialKind::Emissive => material.emission.clamp(),
        MaterialKind::Glass => {
            let eta = if hit.front_face {
                1.0 / material.ior
            } else {
                material.ior
            };
            let cos_i = view.dot(hit.normal).clamp(0.0, 1.0);
            let refracted = refract(direction, hit.normal, eta);
            let reflectance = if refracted.is_some() {
                fresnel(cos_i, eta)
            } else {
                1.0
            };
            let (_, highlight) = phong_light(scene, &hit, view, 256.0, 1.0, rng);
            if !deeper {
                return (background(scene, direction).hadamard(material.color) + highlight).clamp();
            }
            let reflected = whitted(
                scene,
                outside,
                direction.reflect(hit.normal).normalized(),
                depth + 1,
                rng,
            );
            let transmitted = match refracted {
                Some(through) => whitted(scene, inside, through, depth + 1, rng),
                None => Vec3::default(),
            };
            ((reflected * reflectance + transmitted.hadamard(material.color) * (1.0 - reflectance))
                + highlight)
                .clamp()
        }
        MaterialKind::Metal => {
            let shininess: f64 = 2.0 / (material.roughness * material.roughness).max(1e-4);
            let (_, highlight) = phong_light(scene, &hit, view, shininess.min(512.0), 1.0, rng);
            let mut bounce = glossy(
                direction.reflect(hit.normal).normalized(),
                material.roughness,
                rng,
            );
            if bounce.dot(hit.normal) <= 0.0 {
                bounce = direction.reflect(hit.normal).normalized();
            }
            let reflected = if deeper {
                whitted(scene, outside, bounce, depth + 1, rng)
            } else {
                background(scene, bounce)
            };
            (reflected.hadamard(material.color) + highlight.hadamard(material.color)).clamp()
        }
        MaterialKind::Phong | MaterialKind::Diffuse => {
            let (diffuse, highlight) = phong_light(
                scene,
                &hit,
                view,
                material.shininess,
                material.specular,
                rng,
            );
            let local = material.color.hadamard(diffuse) + highlight;
            if !deeper || material.reflectivity <= 0.0 {
                return local.clamp();
            }
            let bounce = glossy(
                direction.reflect(hit.normal).normalized(),
                material.roughness,
                rng,
            );
            let reflected = whitted(scene, outside, bounce, depth + 1, rng);
            (local * (1.0 - material.reflectivity) + reflected * material.reflectivity).clamp()
        }
    }
}

/// Irradiance at a point of normal `normal` from the point lights and one
/// sample of each emitting object (path mode).
fn direct_light(scene: &Scene, point: Vec3, normal: Vec3, rng: &mut Rng) -> Vec3 {
    let origin = point + normal * (EPSILON * 4.0);
    let mut irradiance = Vec3::default();
    for light in &scene.points {
        let displacement = light.position - point;
        let distance_squared = displacement.dot(displacement).max(1e-6);
        let distance = distance_squared.sqrt();
        let direction = displacement / distance;
        let cosine = normal.dot(direction);
        if cosine <= 0.0 {
            continue;
        }
        let through = transmittance(scene, origin, direction, distance, None);
        irradiance = irradiance
            + light.color.hadamard(through)
                * (PI * light.intensity * LIGHT_UNIT * cosine / distance_squared);
    }
    for emitter in &scene.emitters {
        let shape = &scene.shapes[emitter.shape];
        let radiance = scene.materials[scene.shape_material[emitter.shape]].emission;
        let (direction, distance, inverse_pdf) = match *shape {
            Shape::Sphere { center, radius } => {
                let axis = center - point;
                let distance_squared = axis.dot(axis);
                if distance_squared <= radius * radius {
                    continue;
                }
                let cos_max = (1.0 - radius * radius / distance_squared).max(0.0).sqrt();
                let direction = rng.in_cone(axis.normalized(), cos_max);
                let Some((distance, _)) = shape.intersect(origin, direction) else {
                    continue;
                };
                (direction, distance, 2.0 * PI * (1.0 - cos_max))
            }
            Shape::Quad {
                corner,
                u,
                v,
                normal: light_normal,
            } => {
                let target = corner + u * rng.uniform() + v * rng.uniform();
                let (direction, distance, cos_light) = towards(point, target, light_normal);
                if cos_light <= 1e-9 {
                    continue;
                }
                (
                    direction,
                    distance,
                    shape.area() * cos_light / (distance * distance),
                )
            }
            Shape::Triangle {
                a,
                edge1,
                edge2,
                normal: light_normal,
            } => {
                let (mut s, mut t) = (rng.uniform(), rng.uniform());
                if s + t > 1.0 {
                    (s, t) = (1.0 - s, 1.0 - t);
                }
                let target = a + edge1 * s + edge2 * t;
                let (direction, distance, cos_light) = towards(point, target, light_normal);
                if cos_light <= 1e-9 {
                    continue;
                }
                (
                    direction,
                    distance,
                    shape.area() * cos_light / (distance * distance),
                )
            }
            Shape::Plane { .. } => continue,
        };
        let cosine = normal.dot(direction);
        if cosine <= 0.0 {
            continue;
        }
        let through = transmittance(scene, origin, direction, distance, Some(emitter.shape));
        irradiance = irradiance + radiance.hadamard(through) * (cosine * inverse_pdf);
    }
    irradiance
}

/// Direction and distance from `point` to `target`, and the cosine at the
/// (two-sided) light surface.
fn towards(point: Vec3, target: Vec3, light_normal: Vec3) -> (Vec3, f64, f64) {
    let displacement = target - point;
    let distance = displacement.length().max(1e-9);
    let direction = displacement / distance;
    (direction, distance, light_normal.dot(direction).abs())
}

fn linear(color: Vec3) -> Vec3 {
    color.hadamard(color)
}

fn path(scene: &Scene, mut origin: Vec3, mut direction: Vec3, rng: &mut Rng) -> Vec3 {
    let mut throughput = Vec3::new(1.0, 1.0, 1.0);
    let mut radiance = Vec3::default();
    let mut count_emission = true;
    // Once a path has bounced off a rough surface (diffuse, glossy coat,
    // rough metal), a light reached afterwards through glass or a mirror is
    // a rare, very bright sample (a "firefly"): its contribution is capped
    // at `render.clamp` (biased, but clean images).
    let mut after_rough = false;
    let cap = scene.settings.clamp;
    for depth in 0..=scene.settings.bounces {
        let Some(hit) = nearest(scene, origin, direction, f64::INFINITY) else {
            radiance = radiance + throughput.hadamard(background(scene, direction));
            break;
        };
        let material = *material_of(scene, &hit);
        if material.kind == MaterialKind::Emissive {
            if count_emission {
                let mut added = throughput.hadamard(material.emission);
                if after_rough {
                    added = Vec3::new(added.x.min(cap), added.y.min(cap), added.z.min(cap));
                }
                radiance = radiance + added;
            }
            break;
        }
        if depth == scene.settings.bounces {
            break;
        }
        let outside = hit.point + hit.normal * (EPSILON * 4.0);
        let reflected = direction.reflect(hit.normal).normalized();
        let next = match material.kind {
            MaterialKind::Phong | MaterialKind::Diffuse => {
                let coat = if material.kind == MaterialKind::Phong {
                    (material.reflectivity + 0.04 * material.specular).clamp(0.0, 0.95)
                } else {
                    0.0
                };
                if rng.uniform() < coat {
                    let roughness =
                        (2.0_f64 / (material.shininess + 2.0)).sqrt() * 0.5 + material.roughness;
                    let bounce = glossy(reflected, roughness.min(1.0), rng);
                    if bounce.dot(hit.normal) <= 0.0 {
                        break;
                    }
                    count_emission = true;
                    after_rough = true;
                    (outside, bounce)
                } else {
                    let albedo = linear(material.color);
                    let light = direct_light(scene, hit.point, hit.normal, rng);
                    radiance = radiance + throughput.hadamard(albedo).hadamard(light) / PI;
                    throughput = throughput.hadamard(albedo);
                    count_emission = false;
                    after_rough = true;
                    (outside, rng.cosine_hemisphere(hit.normal))
                }
            }
            MaterialKind::Metal => {
                let bounce = glossy(reflected, material.roughness, rng);
                if bounce.dot(hit.normal) <= 0.0 {
                    break;
                }
                throughput = throughput.hadamard(linear(material.color));
                count_emission = true;
                after_rough |= material.roughness > 0.05;
                (outside, bounce)
            }
            MaterialKind::Glass => {
                let eta = if hit.front_face {
                    1.0 / material.ior
                } else {
                    material.ior
                };
                let cos_i = (-direction).dot(hit.normal).clamp(0.0, 1.0);
                throughput = throughput.hadamard(material.color);
                count_emission = true;
                match refract(direction, hit.normal, eta) {
                    Some(through) if rng.uniform() >= fresnel(cos_i, eta) => {
                        (hit.point - hit.normal * (EPSILON * 4.0), through)
                    }
                    _ => (outside, reflected),
                }
            }
            MaterialKind::Emissive => unreachable!(),
        };
        if depth >= 3 {
            let survival = throughput.max_component().clamp(0.05, 1.0);
            if rng.uniform() > survival {
                break;
            }
            throughput = throughput / survival;
        }
        (origin, direction) = next;
    }
    radiance
}

fn tonemap(value: f64, tonemap: Tonemap) -> f64 {
    match tonemap {
        Tonemap::Clamp => value,
        Tonemap::Reinhard => value / (1.0 + value),
        // Narkowicz's fit of the ACES filmic curve.
        Tonemap::Aces => (value * (2.51 * value + 0.03)) / (value * (2.43 * value + 0.59) + 0.14),
    }
    .clamp(0.0, 1.0)
}

/// RGB bytes of pixel (`x`, `y`) of the full image.
pub fn pixel(scene: &Scene, x: usize, y: usize) -> [u8; 3] {
    let settings = &scene.settings;
    let samples = settings.samples.max(1);
    let grid = (f64::from(samples)).sqrt().floor() as u32;
    let strata = grid * grid;
    let frame = settings.frame.round() as i64;
    let camera = &scene.camera;
    let aspect = scene.width as f64 / scene.height as f64;
    let mut sum = Vec3::default();
    for sample in 0..samples {
        let mut rng = Rng::for_sample(x, y, sample, frame, settings.seed);
        let (dx, dy) = if samples == 1 {
            (0.5, 0.5)
        } else if sample < strata {
            (
                (f64::from(sample % grid) + rng.uniform()) / f64::from(grid),
                (f64::from(sample / grid) + rng.uniform()) / f64::from(grid),
            )
        } else {
            (rng.uniform(), rng.uniform())
        };
        let px = (2.0 * (x as f64 + dx) / scene.width as f64 - 1.0) * aspect * camera.tan_half_fov;
        let py = (1.0 - 2.0 * (y as f64 + dy) / scene.height as f64) * camera.tan_half_fov;
        let mut direction = (camera.forward + camera.right * px + camera.up * py).normalized();
        let mut origin = camera.origin;
        if camera.aperture > 0.0 {
            let focus =
                origin + direction * (camera.focus_distance / direction.dot(camera.forward));
            let (u, v) = rng.in_disk();
            origin =
                origin + camera.right * (u * camera.aperture) + camera.up * (v * camera.aperture);
            direction = (focus - origin).normalized();
        }
        let color = match settings.mode {
            Mode::Whitted => whitted(scene, origin, direction, 0, &mut rng),
            Mode::Path => path(scene, origin, direction, &mut rng),
        };
        if color.x.is_finite() && color.y.is_finite() && color.z.is_finite() {
            sum = sum + color;
        }
    }
    let mean = sum * (settings.exposure / f64::from(samples));
    [mean.x, mean.y, mean.z].map(|channel| {
        (tonemap(channel.max(0.0), settings.tonemap).sqrt() * 255.0)
            .round()
            .clamp(0.0, 255.0) as u8
    })
}
