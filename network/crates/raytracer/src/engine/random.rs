//! Deterministic randomness and sampling.
//!
//! Every random number depends only on (pixel, sample, frame, scene seed) and
//! on how many numbers that sample already drew, never on threads or timing:
//! two machines rendering the same tile draw exactly the same numbers, so
//! their pixels (and the milestone hashes) are identical.
//!
//! Transcendental functions come from the `libm` crate (pure Rust), not from
//! the system's maths library, which may differ in the last bit between
//! Windows, Linux and macOS.

use crate::math::Vec3;

pub fn sin(value: f64) -> f64 {
    libm::sin(value)
}
pub fn cos(value: f64) -> f64 {
    libm::cos(value)
}
pub fn tan(value: f64) -> f64 {
    libm::tan(value)
}
pub fn pow(base: f64, exponent: f64) -> f64 {
    libm::pow(base, exponent)
}
pub fn exp(value: f64) -> f64 {
    libm::exp(value)
}

const TAU: f64 = std::f64::consts::TAU;

fn mix(mut value: u64) -> u64 {
    // SplitMix64 finaliser.
    value = (value ^ (value >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
    value = (value ^ (value >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
    value ^ (value >> 31)
}

/// Sequence of random numbers of one sample of one pixel.
pub struct Rng {
    state: u64,
}

impl Rng {
    /// The sequence of sample `sample` of pixel (`x`, `y`) at `frame`.
    pub fn for_sample(x: usize, y: usize, sample: u32, frame: i64, seed: u64) -> Self {
        let mut state = mix(seed ^ 0x5131_c1d1_0000_0002);
        for part in [x as u64, y as u64, u64::from(sample), frame as u64] {
            state = mix(state ^ part.wrapping_add(0x9e37_79b9_7f4a_7c15));
        }
        Rng { state }
    }

    /// Next number in `[0, 1)`.
    pub fn uniform(&mut self) -> f64 {
        self.state = self.state.wrapping_add(0x9e37_79b9_7f4a_7c15);
        (mix(self.state) >> 11) as f64 / (1_u64 << 53) as f64
    }

    /// Uniform point in the unit disk.
    pub fn in_disk(&mut self) -> (f64, f64) {
        let radius = self.uniform().sqrt();
        let angle = TAU * self.uniform();
        (radius * cos(angle), radius * sin(angle))
    }

    /// Uniform point inside the unit sphere.
    pub fn in_sphere(&mut self) -> Vec3 {
        let direction = self.on_sphere();
        let radius = libm::cbrt(self.uniform());
        direction * radius
    }

    /// Uniform direction.
    pub fn on_sphere(&mut self) -> Vec3 {
        let z = 1.0 - 2.0 * self.uniform();
        let r = (1.0 - z * z).max(0.0).sqrt();
        let angle = TAU * self.uniform();
        Vec3::new(r * cos(angle), r * sin(angle), z)
    }

    /// Cosine-weighted direction around `normal` (pdf = cos θ / π).
    pub fn cosine_hemisphere(&mut self, normal: Vec3) -> Vec3 {
        let (u, v) = self.in_disk();
        let w = (1.0 - u * u - v * v).max(0.0).sqrt();
        let (tangent, bitangent) = basis(normal);
        (tangent * u + bitangent * v + normal * w).normalized()
    }

    /// Uniform direction in the cone of half-angle `acos(cos_max)` around
    /// `axis` (pdf = 1 / (2π (1 − cos_max))).
    pub fn in_cone(&mut self, axis: Vec3, cos_max: f64) -> Vec3 {
        let cos_theta = 1.0 - self.uniform() * (1.0 - cos_max);
        let sin_theta = (1.0 - cos_theta * cos_theta).max(0.0).sqrt();
        let angle = TAU * self.uniform();
        let (tangent, bitangent) = basis(axis);
        (tangent * (sin_theta * cos(angle))
            + bitangent * (sin_theta * sin(angle))
            + axis * cos_theta)
            .normalized()
    }
}

/// Two unit vectors perpendicular to `normal` and to each other.
pub fn basis(normal: Vec3) -> (Vec3, Vec3) {
    // Duff et al., "Building an Orthonormal Basis, Revisited" (2017).
    let sign = if normal.z >= 0.0 { 1.0 } else { -1.0 };
    let a = -1.0 / (sign + normal.z);
    let b = normal.x * normal.y * a;
    (
        Vec3::new(
            1.0 + sign * normal.x * normal.x * a,
            sign * b,
            -sign * normal.x,
        ),
        Vec3::new(b, sign + normal.y * normal.y * a, -normal.y),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_pixel_same_numbers_other_pixel_other_numbers() {
        let draw = |x, y, s| {
            let mut rng = Rng::for_sample(x, y, s, 0, 7);
            (0..4).map(|_| rng.uniform()).collect::<Vec<_>>()
        };
        assert_eq!(draw(3, 4, 0), draw(3, 4, 0));
        assert_ne!(draw(3, 4, 0), draw(4, 3, 0));
        assert_ne!(draw(3, 4, 0), draw(3, 4, 1));
        assert!(draw(1, 2, 3).iter().all(|v| (0.0..1.0).contains(v)));
    }

    #[test]
    fn sampled_directions_are_unit_and_on_the_right_side() {
        let mut rng = Rng::for_sample(0, 0, 0, 0, 0);
        let normal = Vec3::new(0.3, -0.5, 0.8).normalized();
        for _ in 0..200 {
            let d = rng.cosine_hemisphere(normal);
            assert!((d.length() - 1.0).abs() < 1e-9 && d.dot(normal) >= -1e-9);
            let c = rng.in_cone(normal, 0.9);
            assert!(c.dot(normal) >= 0.9 - 1e-9);
        }
    }
}
