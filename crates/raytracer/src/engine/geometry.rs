//! Geometry: spheres, planes, triangles and parallelograms ("quads"),
//! object transforms, and the bounding-volume hierarchy (BVH) that keeps
//! scenes with many triangles fast.

use super::random::{cos, sin};
use crate::{math::Vec3, EPSILON};

/// Shape of an object, in world coordinates.
#[derive(Clone, Debug)]
pub enum Shape {
    Sphere {
        center: Vec3,
        radius: f64,
    },
    Plane {
        point: Vec3,
        normal: Vec3,
    },
    Triangle {
        a: Vec3,
        edge1: Vec3,
        edge2: Vec3,
        normal: Vec3,
    },
    /// Parallelogram `corner + s·u + t·v`, `s, t` in `[0, 1]`.
    Quad {
        corner: Vec3,
        u: Vec3,
        v: Vec3,
        normal: Vec3,
    },
}

impl Shape {
    pub fn triangle(a: Vec3, b: Vec3, c: Vec3) -> Shape {
        let (edge1, edge2) = (b - a, c - a);
        Shape::Triangle {
            a,
            edge1,
            edge2,
            normal: edge1.cross(edge2).normalized(),
        }
    }

    pub fn quad(corner: Vec3, u: Vec3, v: Vec3) -> Shape {
        Shape::Quad {
            corner,
            u,
            v,
            normal: u.cross(v).normalized(),
        }
    }

    /// Distance and outward normal of the first hit after `EPSILON`.
    pub fn intersect(&self, origin: Vec3, direction: Vec3) -> Option<(f64, Vec3)> {
        match *self {
            Shape::Sphere { center, radius } => {
                let offset = origin - center;
                let half_b = offset.dot(direction);
                let c = offset.dot(offset) - radius * radius;
                let discriminant = half_b * half_b - c;
                if discriminant < 0.0 {
                    return None;
                }
                let root = discriminant.sqrt();
                let distance = [-half_b - root, -half_b + root]
                    .into_iter()
                    .find(|t| *t > EPSILON)?;
                let point = origin + direction * distance;
                Some((distance, (point - center) / radius))
            }
            Shape::Plane { point, normal } => {
                let denominator = normal.dot(direction);
                if denominator.abs() < 1e-12 {
                    return None;
                }
                let distance = (point - origin).dot(normal) / denominator;
                (distance > EPSILON).then_some((distance, normal))
            }
            Shape::Triangle {
                a,
                edge1,
                edge2,
                normal,
            } => {
                let p = direction.cross(edge2);
                let determinant = edge1.dot(p);
                if determinant.abs() < 1e-12 {
                    return None;
                }
                let inverse = 1.0 / determinant;
                let s = origin - a;
                let u = s.dot(p) * inverse;
                if !(0.0..=1.0).contains(&u) {
                    return None;
                }
                let q = s.cross(edge1);
                let v = direction.dot(q) * inverse;
                if v < 0.0 || u + v > 1.0 {
                    return None;
                }
                let distance = edge2.dot(q) * inverse;
                (distance > EPSILON).then_some((distance, normal))
            }
            Shape::Quad {
                corner,
                u,
                v,
                normal,
            } => {
                let denominator = normal.dot(direction);
                if denominator.abs() < 1e-12 {
                    return None;
                }
                let distance = (corner - origin).dot(normal) / denominator;
                if distance <= EPSILON {
                    return None;
                }
                let relative = origin + direction * distance - corner;
                let n = u.cross(v);
                let w = n / n.dot(n);
                let alpha = w.dot(relative.cross(v));
                let beta = w.dot(u.cross(relative));
                ((0.0..=1.0).contains(&alpha) && (0.0..=1.0).contains(&beta))
                    .then_some((distance, normal))
            }
        }
    }

    /// Bounding box, `None` for an infinite plane.
    pub fn bounds(&self) -> Option<Aabb> {
        let pad = Vec3::new(1e-6, 1e-6, 1e-6);
        match *self {
            Shape::Sphere { center, radius } => {
                let r = Vec3::new(radius, radius, radius);
                Some(Aabb {
                    min: center - r,
                    max: center + r,
                })
            }
            Shape::Plane { .. } => None,
            Shape::Triangle {
                a, edge1, edge2, ..
            } => {
                let mut bounds = Aabb::point(a);
                bounds.grow(a + edge1);
                bounds.grow(a + edge2);
                Some(Aabb {
                    min: bounds.min - pad,
                    max: bounds.max + pad,
                })
            }
            Shape::Quad { corner, u, v, .. } => {
                let mut bounds = Aabb::point(corner);
                for point in [corner + u, corner + v, corner + u + v] {
                    bounds.grow(point);
                }
                Some(Aabb {
                    min: bounds.min - pad,
                    max: bounds.max + pad,
                })
            }
        }
    }

    /// Surface area (spheres, triangles, quads).
    pub fn area(&self) -> f64 {
        match *self {
            Shape::Sphere { radius, .. } => 4.0 * std::f64::consts::PI * radius * radius,
            Shape::Plane { .. } => f64::INFINITY,
            Shape::Triangle { edge1, edge2, .. } => 0.5 * edge1.cross(edge2).length(),
            Shape::Quad { u, v, .. } => u.cross(v).length(),
        }
    }
}

/// Axis-aligned bounding box.
#[derive(Clone, Copy, Debug)]
pub struct Aabb {
    pub min: Vec3,
    pub max: Vec3,
}

impl Aabb {
    pub fn point(point: Vec3) -> Aabb {
        Aabb {
            min: point,
            max: point,
        }
    }

    pub fn grow(&mut self, point: Vec3) {
        self.min = Vec3::new(
            self.min.x.min(point.x),
            self.min.y.min(point.y),
            self.min.z.min(point.z),
        );
        self.max = Vec3::new(
            self.max.x.max(point.x),
            self.max.y.max(point.y),
            self.max.z.max(point.z),
        );
    }

    pub fn merge(&mut self, other: &Aabb) {
        self.grow(other.min);
        self.grow(other.max);
    }

    pub fn centre(&self) -> Vec3 {
        (self.min + self.max) * 0.5
    }

    /// True when the ray enters the box before `limit`.
    pub fn hit(&self, origin: Vec3, inverse: Vec3, limit: f64) -> bool {
        let mut near = 0.0_f64;
        let mut far = limit;
        for axis in 0..3 {
            let a = (self.min.axis(axis) - origin.axis(axis)) * inverse.axis(axis);
            let b = (self.max.axis(axis) - origin.axis(axis)) * inverse.axis(axis);
            let (low, high) = if a <= b { (a, b) } else { (b, a) };
            // NaN (0 × ∞ on an axis-parallel ray at a slab edge) never shrinks the interval.
            if low > near {
                near = low;
            }
            if high < far {
                far = high;
            }
            if near > far {
                return false;
            }
        }
        true
    }
}

/// Scale, then rotation (degrees around x, then y, then z), then translation.
#[derive(Clone, Copy, Debug)]
pub struct Transform {
    scale: Vec3,
    rotation: [Vec3; 3],
    translation: Vec3,
}

impl Default for Transform {
    fn default() -> Self {
        Transform {
            scale: Vec3::new(1.0, 1.0, 1.0),
            rotation: [
                Vec3::new(1.0, 0.0, 0.0),
                Vec3::new(0.0, 1.0, 0.0),
                Vec3::new(0.0, 0.0, 1.0),
            ],
            translation: Vec3::default(),
        }
    }
}

impl Transform {
    pub fn new(scale: Vec3, rotation_degrees: Vec3, translation: Vec3) -> Transform {
        let (ax, ay, az) = (
            rotation_degrees.x.to_radians(),
            rotation_degrees.y.to_radians(),
            rotation_degrees.z.to_radians(),
        );
        let (sx, cx, sy, cy, sz, cz) = (sin(ax), cos(ax), sin(ay), cos(ay), sin(az), cos(az));
        // Rows of Rz · Ry · Rx.
        let rotation = [
            Vec3::new(cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
            Vec3::new(sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
            Vec3::new(-sy, cy * sx, cy * cx),
        ];
        Transform {
            scale,
            rotation,
            translation,
        }
    }

    fn rotate(&self, vector: Vec3) -> Vec3 {
        Vec3::new(
            self.rotation[0].dot(vector),
            self.rotation[1].dot(vector),
            self.rotation[2].dot(vector),
        )
    }

    /// A point of the object in world coordinates.
    pub fn point(&self, point: Vec3) -> Vec3 {
        self.rotate(point.hadamard(self.scale)) + self.translation
    }

    /// An edge (a difference of points) in world coordinates.
    pub fn vector(&self, vector: Vec3) -> Vec3 {
        self.rotate(vector.hadamard(self.scale))
    }

    /// A surface normal in world coordinates.
    pub fn normal(&self, normal: Vec3) -> Vec3 {
        self.rotate(Vec3::new(
            normal.x / self.scale.x,
            normal.y / self.scale.y,
            normal.z / self.scale.z,
        ))
        .normalized()
    }

    /// Largest scale factor (spheres stay round).
    pub fn uniform_scale(&self) -> f64 {
        self.scale
            .x
            .abs()
            .max(self.scale.y.abs())
            .max(self.scale.z.abs())
    }
}

/// Node of the BVH: a leaf holds `count` objects from `first` in the
/// ordered index list, an inner node its two children.
#[derive(Clone, Debug)]
struct Node {
    bounds: Aabb,
    first: usize,
    count: usize,
    left: usize,
    right: usize,
}

/// Bounding-volume hierarchy over the finite shapes.
#[derive(Clone, Debug, Default)]
pub struct Bvh {
    nodes: Vec<Node>,
    order: Vec<usize>,
}

const LEAF_SIZE: usize = 4;

impl Bvh {
    /// Builds the tree over `shapes[i]` for the indices in `members`
    /// (deterministic: median split on the longest axis, ties by index).
    pub fn build(shapes: &[Shape], members: Vec<usize>) -> Bvh {
        let boxes: Vec<Option<Aabb>> = shapes.iter().map(Shape::bounds).collect();
        let mut bvh = Bvh {
            nodes: Vec::new(),
            order: members,
        };
        if !bvh.order.is_empty() {
            let count = bvh.order.len();
            bvh.split(&boxes, 0, count);
        }
        bvh
    }

    fn split(&mut self, boxes: &[Option<Aabb>], first: usize, count: usize) -> usize {
        let items = &mut self.order[first..first + count];
        let bounds_of = |index: usize| boxes[index].expect("finite shape");
        let mut bounds = bounds_of(items[0]);
        let mut centres = Aabb::point(bounds.centre());
        for &item in items.iter() {
            bounds.merge(&bounds_of(item));
            centres.grow(bounds_of(item).centre());
        }
        let node = self.nodes.len();
        self.nodes.push(Node {
            bounds,
            first,
            count,
            left: 0,
            right: 0,
        });
        if count <= LEAF_SIZE {
            return node;
        }
        let extent = centres.max - centres.min;
        let axis = if extent.x >= extent.y && extent.x >= extent.z {
            0
        } else if extent.y >= extent.z {
            1
        } else {
            2
        };
        items.sort_by(|a, b| {
            bounds_of(*a)
                .centre()
                .axis(axis)
                .total_cmp(&bounds_of(*b).centre().axis(axis))
                .then(a.cmp(b))
        });
        let half = count / 2;
        let left = self.split(boxes, first, half);
        let right = self.split(boxes, first + half, count - half);
        let inner = &mut self.nodes[node];
        inner.count = 0;
        inner.left = left;
        inner.right = right;
        node
    }

    /// Nearest hit among the members: `(distance, normal, shape index)`.
    pub fn intersect(
        &self,
        shapes: &[Shape],
        origin: Vec3,
        direction: Vec3,
        limit: f64,
    ) -> Option<(f64, Vec3, usize)> {
        if self.nodes.is_empty() {
            return None;
        }
        let inverse = Vec3::new(1.0 / direction.x, 1.0 / direction.y, 1.0 / direction.z);
        let mut best: Option<(f64, Vec3, usize)> = None;
        let mut stack = vec![0_usize];
        while let Some(index) = stack.pop() {
            let node = &self.nodes[index];
            let reach = best.map(|hit| hit.0).unwrap_or(limit);
            if !node.bounds.hit(origin, inverse, reach) {
                continue;
            }
            if node.count > 0 {
                for &member in &self.order[node.first..node.first + node.count] {
                    if let Some((distance, normal)) = shapes[member].intersect(origin, direction) {
                        let better = match best {
                            Some((current, _, current_index)) => {
                                distance < current
                                    || (distance == current && member < current_index)
                            }
                            None => distance < limit,
                        };
                        if better {
                            best = Some((distance, normal, member));
                        }
                    }
                }
            } else {
                stack.push(node.right);
                stack.push(node.left);
            }
        }
        best
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn brute(shapes: &[Shape], origin: Vec3, direction: Vec3) -> Option<(f64, usize)> {
        let mut best: Option<(f64, usize)> = None;
        for (index, shape) in shapes.iter().enumerate() {
            if let Some((distance, _)) = shape.intersect(origin, direction) {
                if best.is_none_or(|(current, current_index)| {
                    distance < current || (distance == current && index < current_index)
                }) {
                    best = Some((distance, index));
                }
            }
        }
        best
    }

    #[test]
    fn bvh_finds_the_same_hits_as_testing_every_shape() {
        let mut shapes = Vec::new();
        for i in 0..40 {
            let f = i as f64;
            shapes.push(Shape::triangle(
                Vec3::new(5.0 + (f * 0.37).sin(), f * 0.1 - 2.0, (f * 0.7).cos()),
                Vec3::new(5.5 + (f * 0.13).cos(), f * 0.1 - 1.6, (f * 0.3).sin()),
                Vec3::new(4.8, f * 0.1 - 1.8, 0.6 + (f * 0.2).sin()),
            ));
            shapes.push(Shape::Sphere {
                center: Vec3::new(7.0 + f * 0.05, (f * 0.9).sin() * 2.0, (f * 0.4).cos()),
                radius: 0.15,
            });
        }
        let bvh = Bvh::build(&shapes, (0..shapes.len()).collect());
        for y in 0..30 {
            for z in 0..30 {
                let direction =
                    Vec3::new(1.0, (y as f64 - 15.0) / 12.0, (z as f64 - 15.0) / 12.0).normalized();
                let fast = bvh
                    .intersect(&shapes, Vec3::default(), direction, f64::INFINITY)
                    .map(|h| (h.0, h.2));
                assert_eq!(fast, brute(&shapes, Vec3::default(), direction));
            }
        }
    }

    #[test]
    fn transforms_scale_rotate_then_translate() {
        let t = Transform::new(
            Vec3::new(2.0, 2.0, 2.0),
            Vec3::new(0.0, 0.0, 90.0),
            Vec3::new(1.0, 0.0, 0.0),
        );
        let p = t.point(Vec3::new(1.0, 0.0, 0.0));
        assert!((p - Vec3::new(1.0, 2.0, 0.0)).length() < 1e-12);
        let n = t.normal(Vec3::new(1.0, 0.0, 0.0));
        assert!((n - Vec3::new(0.0, 1.0, 0.0)).length() < 1e-12);
    }

    #[test]
    fn quads_and_triangles_are_hit_inside_only() {
        let quad = Shape::quad(
            Vec3::new(5.0, -1.0, -1.0),
            Vec3::new(0.0, 2.0, 0.0),
            Vec3::new(0.0, 0.0, 2.0),
        );
        assert!(quad
            .intersect(Vec3::default(), Vec3::new(1.0, 0.0, 0.0))
            .is_some());
        assert!(quad
            .intersect(Vec3::default(), Vec3::new(1.0, 0.5, 0.0).normalized())
            .is_none());
        assert!((quad.area() - 4.0).abs() < 1e-12);
    }
}
