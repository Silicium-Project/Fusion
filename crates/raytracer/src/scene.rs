//! Scene description ([`Scene`], [`Primitive`], [`Material`], [`Light`]) and
//! ray/primitive intersection.

use crate::{
    math::{Ray, Vec3},
    EPSILON,
};

#[derive(Clone, Copy)]
pub struct Material {
    pub color: Vec3,
    pub reflectivity: f64,
    pub specular: f64,
    pub shininess: f64,
}

#[derive(Clone)]
pub enum Primitive {
    Sphere {
        center: Vec3,
        radius: f64,
        material: Material,
    },
    Plane {
        point: Vec3,
        normal: Vec3,
        material: Material,
    },
}

#[derive(Clone, Copy)]
pub struct Light {
    pub position: Vec3,
    pub intensity: f64,
    pub color: Vec3,
}

#[derive(Clone)]
pub struct Scene {
    pub width: usize,
    pub height: usize,
    pub fov: f64,
    pub camera: Vec3,
    pub primitives: Vec<Primitive>,
    pub lights: Vec<Light>,
}

#[derive(Clone, Copy)]
pub struct Hit {
    pub distance: f64,
    pub point: Vec3,
    pub normal: Vec3,
    pub material: Material,
}

impl Primitive {
    pub fn intersect(&self, ray: Ray) -> Option<Hit> {
        match self {
            Primitive::Sphere {
                center,
                radius,
                material,
            } => {
                let offset = ray.origin - *center;
                let half_b = offset.dot(ray.direction);
                let c = offset.dot(offset) - radius * radius;
                let discriminant = half_b * half_b - c;
                if discriminant < 0.0 {
                    return None;
                }
                let root = discriminant.sqrt();
                let first = -half_b - root;
                let second = -half_b + root;
                let distance = if first > EPSILON {
                    first
                } else if second > EPSILON {
                    second
                } else {
                    return None;
                };
                let point = ray.origin + ray.direction * distance;
                Some(Hit {
                    distance,
                    point,
                    normal: (point - *center).normalized(),
                    material: *material,
                })
            }
            Primitive::Plane {
                point,
                normal,
                material,
            } => {
                let denominator = normal.dot(ray.direction);
                if denominator.abs() < EPSILON {
                    return None;
                }
                let distance = (*point - ray.origin).dot(*normal) / denominator;
                if distance <= EPSILON {
                    return None;
                }
                Some(Hit {
                    distance,
                    point: ray.origin + ray.direction * distance,
                    normal: if denominator < 0.0 { *normal } else { -*normal },
                    material: *material,
                })
            }
        }
    }
}
