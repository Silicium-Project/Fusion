//! Scene: built from the syntax tree for one animation frame.
//!
//! See the README for the file format: rays per pixel and lighting mode
//! (`render`), a free camera (`look_at`, `direction`, `rotation`, depth of
//! field), named materials (`phong`, `diffuse`, `metal`, `glass`,
//! `emissive`), spheres, planes, boxes, triangles, quads and meshes with
//! transforms, point and area lights, and keyframes.

use super::{
    geometry::{Bvh, Shape, Transform},
    random::tan,
    syntax::{self, BlockExt, Entry, Value},
    ENGINE_VERSION,
};
use crate::{math::Vec3, EPSILON};
use std::collections::HashMap;

/// How light is computed.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    /// Classic lighting (Phong highlights, mirror reflections, hard or soft
    /// shadows from `point` and `area` lights), plus glass and metal.
    Whitted,
    /// Monte-Carlo path tracing: indirect light, soft shadows, emissive objects.
    Path,
}

/// How colours above 1 are brought back to the screen.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Tonemap {
    Clamp,
    Reinhard,
    Aces,
}

/// The `render` block.
#[derive(Clone, Debug)]
pub struct Settings {
    pub samples: u32,
    pub mode: Mode,
    pub bounces: u32,
    pub exposure: f64,
    pub tonemap: Tonemap,
    /// Strength of the sky (background and, in path mode, its light).
    pub sky: f64,
    pub seed: u64,
    pub frame: f64,
    /// Largest contribution of a light reached after a diffuse bounce
    /// (path mode; removes "fireflies").
    pub clamp: f64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MaterialKind {
    Phong,
    Diffuse,
    Metal,
    Glass,
    Emissive,
}

#[derive(Clone, Copy, Debug)]
pub struct Material {
    pub kind: MaterialKind,
    /// Colour in `0..=1` (written `0..=255` in scene files).
    pub color: Vec3,
    pub reflectivity: f64,
    pub specular: f64,
    pub shininess: f64,
    pub roughness: f64,
    pub ior: f64,
    /// Emitted radiance (emissive materials and area lights).
    pub emission: Vec3,
}

/// Point light (`intensity` 450 at 5 units is bright).
#[derive(Clone, Copy, Debug)]
pub struct PointLight {
    pub position: Vec3,
    pub intensity: f64,
    pub color: Vec3,
}

/// An object that emits light and is sampled for direct lighting.
#[derive(Clone, Copy, Debug)]
pub struct Emitter {
    /// Index in `Scene::shapes`.
    pub shape: usize,
    /// For `area` lights: their intensity, used by the Whitted mode.
    pub intensity: Option<f64>,
    pub color: Vec3,
}

#[derive(Clone, Copy, Debug)]
pub struct Camera {
    pub origin: Vec3,
    pub forward: Vec3,
    pub right: Vec3,
    pub up: Vec3,
    pub tan_half_fov: f64,
    pub aperture: f64,
    pub focus_distance: f64,
}

/// A scene ready to render (one frame).
#[derive(Clone, Debug)]
pub struct Scene {
    pub width: usize,
    pub height: usize,
    pub camera: Camera,
    pub settings: Settings,
    pub shapes: Vec<Shape>,
    pub shape_material: Vec<usize>,
    pub materials: Vec<Material>,
    pub planes: Vec<usize>,
    pub bvh: Bvh,
    pub points: Vec<PointLight>,
    pub emitters: Vec<Emitter>,
}

/// Scale of light intensities in path mode: a light of intensity 450 at 5
/// units lights a white surface about as much as in Whitted mode.
pub const LIGHT_UNIT: f64 = 1.0 / 12.0;

fn vec3(block: Option<&[Entry]>, default: Vec3, frame: f64) -> Vec3 {
    let Some(block) = block else {
        return default;
    };
    let bare = block.numbers();
    if bare.len() == 3 {
        return Vec3::new(bare[0], bare[1], bare[2]);
    }
    Vec3::new(
        block.number("x", default.x, frame),
        block.number("y", default.y, frame),
        block.number("z", default.z, frame),
    )
}

fn color(block: &[Entry], default: f64, frame: f64) -> Vec3 {
    let source = block.block("color").unwrap_or(block);
    let bare = block
        .block("color")
        .map(|c| c.numbers())
        .unwrap_or_default();
    if bare.len() == 3 {
        return Vec3::new(bare[0], bare[1], bare[2]) / 255.0;
    }
    Vec3::new(
        source.number("r", block.number("r", default, frame), frame),
        source.number("g", block.number("g", default, frame), frame),
        source.number("b", block.number("b", default, frame), frame),
    ) / 255.0
}

fn transform(block: &[Entry], frame: f64) -> Transform {
    let scale = match block.entry("scale").map(|entry| &entry.value) {
        Some(Value::Block(inner)) if syntax::keyframes(inner).is_none() => {
            vec3(Some(inner.as_slice()), Vec3::new(1.0, 1.0, 1.0), frame)
        }
        Some(value) => {
            let s = syntax::evaluate(value, frame).unwrap_or(1.0);
            Vec3::new(s, s, s)
        }
        None => Vec3::new(1.0, 1.0, 1.0),
    };
    Transform::new(
        scale,
        vec3(block.block("rotate"), Vec3::default(), frame),
        vec3(block.block("translate"), Vec3::default(), frame),
    )
}

fn material_kind(word: &str) -> Result<MaterialKind, String> {
    Ok(match word {
        "phong" => MaterialKind::Phong,
        "diffuse" => MaterialKind::Diffuse,
        "metal" => MaterialKind::Metal,
        "glass" => MaterialKind::Glass,
        "emissive" => MaterialKind::Emissive,
        other => return Err(format!("unknown material type `{other}`")),
    })
}

/// A material from the keys of `block` (a `material` block or an object).
fn material(block: &[Entry], default_reflectivity: f64, frame: f64) -> Result<Material, String> {
    let kind = block
        .word("type")
        .map(material_kind)
        .transpose()?
        .unwrap_or(MaterialKind::Phong);
    let color = color(block, 200.0, frame);
    let (reflectivity, specular) = match kind {
        MaterialKind::Diffuse => (0.0, 0.0),
        _ => (
            block
                .number(
                    "reflectivity",
                    block.number("reflection", default_reflectivity, frame),
                    frame,
                )
                .clamp(0.0, 0.95),
            block.number("specular", 0.65, frame).clamp(0.0, 2.0),
        ),
    };
    let strength = block.number("strength", 1.0, frame).max(0.0);
    Ok(Material {
        kind,
        color,
        reflectivity,
        specular,
        shininess: block.number("shininess", 72.0, frame).clamp(1.0, 512.0),
        roughness: block.number("roughness", 0.0, frame).clamp(0.0, 1.0),
        ior: block.number("ior", 1.5, frame).clamp(1.0, 3.0),
        emission: if kind == MaterialKind::Emissive {
            color.hadamard(color) * strength
        } else {
            Vec3::default()
        },
    })
}

const MATERIAL_KEYS: [&str; 12] = [
    "type",
    "color",
    "r",
    "g",
    "b",
    "reflection",
    "reflectivity",
    "specular",
    "shininess",
    "roughness",
    "ior",
    "strength",
];

struct Builder {
    frame: f64,
    shapes: Vec<Shape>,
    shape_material: Vec<usize>,
    materials: Vec<Material>,
    named: HashMap<String, usize>,
}

impl Builder {
    /// Material of an object: `material = name`, else its own keys.
    fn object_material(
        &mut self,
        block: &[Entry],
        default_reflectivity: f64,
    ) -> Result<usize, String> {
        if let Some(name) = block.word("material") {
            let base = *self.named.get(name).ok_or_else(|| {
                format!(
                    "line {}: unknown material `{name}`",
                    block.entry("material").map_or(0, |e| e.line)
                )
            })?;
            // Keys written on the object override the named material.
            if !MATERIAL_KEYS.iter().any(|key| block.entry(key).is_some()) {
                return Ok(base);
            }
        }
        let own = material(block, default_reflectivity, self.frame)?;
        self.materials.push(own);
        Ok(self.materials.len() - 1)
    }

    fn add(&mut self, shape: Shape, material: usize) {
        self.shapes.push(shape);
        self.shape_material.push(material);
    }

    fn primitive(&mut self, name: &str, block: &[Entry], line: usize) -> Result<(), String> {
        let frame = self.frame;
        let t = transform(block, frame);
        let n = |key: &str, default: f64| block.number(key, default, frame);
        match name {
            "sphere" => {
                let material = self.object_material(block, 0.32)?;
                let center = t.point(Vec3::new(n("x", 0.0), n("y", 0.0), n("z", 0.0)));
                let radius = (n("radius", 1.0) * t.uniform_scale()).max(EPSILON);
                self.add(Shape::Sphere { center, radius }, material);
            }
            "plane" => {
                let material = self.object_material(block, 0.12)?;
                let normal = match block.block("normal") {
                    Some(inner) => vec3(Some(inner), Vec3::new(0.0, 0.0, 1.0), frame),
                    None => Vec3::new(n("normal_x", 0.0), n("normal_y", 0.0), n("normal_z", 1.0)),
                };
                if normal.length() <= EPSILON {
                    return Err(format!("line {line}: plane normal is (0, 0, 0)"));
                }
                let point = t.point(Vec3::new(n("x", 0.0), n("y", 0.0), n("z", 0.0)));
                self.add(
                    Shape::Plane {
                        point,
                        normal: t.normal(normal.normalized()),
                    },
                    material,
                );
            }
            "box" => {
                let material = self.object_material(block, 0.12)?;
                let low = vec3(block.block("min"), Vec3::new(-0.5, -0.5, -0.5), frame);
                let high = vec3(block.block("max"), Vec3::new(0.5, 0.5, 0.5), frame);
                let corner = |i: usize| {
                    t.point(Vec3::new(
                        if i & 1 == 0 { low.x } else { high.x },
                        if i & 2 == 0 { low.y } else { high.y },
                        if i & 4 == 0 { low.z } else { high.z },
                    ))
                };
                // Faces as quads (corner, two edges), normals outward.
                for (a, b, c) in [
                    (0, 2, 1),
                    (4, 5, 6),
                    (0, 1, 4),
                    (2, 6, 3),
                    (0, 4, 2),
                    (1, 3, 5),
                ] {
                    let origin = corner(a);
                    self.add(
                        Shape::quad(origin, corner(b) - origin, corner(c) - origin),
                        material,
                    );
                }
            }
            "triangle" => {
                let material = self.object_material(block, 0.12)?;
                let a = t.point(vec3(block.block("a"), Vec3::default(), frame));
                let b = t.point(vec3(block.block("b"), Vec3::new(0.0, 1.0, 0.0), frame));
                let c = t.point(vec3(block.block("c"), Vec3::new(0.0, 0.0, 1.0), frame));
                self.add(Shape::triangle(a, b, c), material);
            }
            "quad" => {
                let material = self.object_material(block, 0.12)?;
                let corner = t.point(vec3(
                    block.block("corner"),
                    Vec3::new(0.0, -0.5, -0.5),
                    frame,
                ));
                let u = t.vector(vec3(block.block("u"), Vec3::new(0.0, 1.0, 0.0), frame));
                let v = t.vector(vec3(block.block("v"), Vec3::new(0.0, 0.0, 1.0), frame));
                self.add(Shape::quad(corner, u, v), material);
            }
            "mesh" => {
                let material = self.object_material(block, 0.12)?;
                let vertices = block
                    .block("vertices")
                    .map(|v| v.numbers())
                    .unwrap_or_default();
                let faces = block
                    .block("faces")
                    .map(|f| f.numbers())
                    .unwrap_or_default();
                if !vertices.len().is_multiple_of(3) || !faces.len().is_multiple_of(3) {
                    return Err(format!(
                        "line {line}: mesh vertices and faces must be groups of 3 numbers"
                    ));
                }
                let points: Vec<Vec3> = vertices
                    .chunks(3)
                    .map(|v| t.point(Vec3::new(v[0], v[1], v[2])))
                    .collect();
                for face in faces.chunks(3) {
                    let index = |value: f64| {
                        let i = value as usize;
                        (value >= 0.0 && value.fract() == 0.0 && i < points.len())
                            .then_some(i)
                            .ok_or_else(|| {
                                format!(
                                    "line {line}: mesh face uses vertex {value}, the mesh has {}",
                                    points.len()
                                )
                            })
                    };
                    let (a, b, c) = (index(face[0])?, index(face[1])?, index(face[2])?);
                    self.add(Shape::triangle(points[a], points[b], points[c]), material);
                }
            }
            _ => {}
        }
        Ok(())
    }
}

fn camera(block: &[Entry], frame: f64) -> Camera {
    let n = |key: &str, default: f64| block.number(key, default, frame);
    let position = match block.block("position") {
        Some(inner) => vec3(Some(inner), Vec3::default(), frame),
        None => Vec3::new(n("x", 0.0), n("y", 0.0), n("z", 0.0)),
    };
    let look_at = block
        .block("look_at")
        .map(|inner| vec3(Some(inner), Vec3::new(1.0, 0.0, 0.0), frame));
    let up_hint = vec3(block.block("up"), Vec3::new(0.0, 0.0, 1.0), frame).normalized();
    let mut up_hint = if up_hint.length() <= EPSILON {
        Vec3::new(0.0, 0.0, 1.0)
    } else {
        up_hint
    };
    let mut forward = if let Some(target) = look_at {
        target - position
    } else if let Some(direction) = block.block("direction") {
        vec3(Some(direction), Vec3::new(1.0, 0.0, 0.0), frame)
    } else {
        Vec3::new(1.0, 0.0, 0.0)
    }
    .normalized();
    if forward.length() <= EPSILON {
        forward = Vec3::new(1.0, 0.0, 0.0);
    }
    if look_at.is_none() {
        if let Some(rotation) = block.block("rotation") {
            let turn = Transform::new(
                Vec3::new(1.0, 1.0, 1.0),
                vec3(Some(rotation), Vec3::default(), frame),
                Vec3::default(),
            );
            forward = turn.vector(forward).normalized();
            up_hint = turn.vector(up_hint).normalized();
        }
    }
    if forward.cross(up_hint).length() <= 1e-9 {
        up_hint = if forward.z.abs() > 0.9 {
            Vec3::new(1.0, 0.0, 0.0)
        } else {
            Vec3::new(0.0, 0.0, 1.0)
        };
    }
    let right = forward.cross(up_hint).normalized();
    let up = right.cross(forward).normalized();
    let fov = n("fieldOfView", 55.0).clamp(1.0, 179.0);
    let aperture = n("aperture", 0.0).max(0.0);
    let focus_distance = n(
        "focus_distance",
        look_at
            .map(|target| (target - position).length())
            .unwrap_or(5.0),
    )
    .max(EPSILON);
    Camera {
        origin: position,
        forward,
        right,
        up,
        tan_half_fov: tan(fov.to_radians() * 0.5),
        aperture,
        focus_distance,
    }
}

fn settings(root: &[Entry], frame_override: Option<f64>) -> Result<Settings, String> {
    let empty: &[Entry] = &[];
    let render = root.block("render").unwrap_or(empty);
    let engine = render.number("engine", f64::from(ENGINE_VERSION), 0.0);
    if engine > f64::from(ENGINE_VERSION) {
        return Err(format!(
            "scene_requires_engine:{engine} (this engine is {ENGINE_VERSION})"
        ));
    }
    let mode = match render.word("mode").unwrap_or("whitted") {
        "whitted" => Mode::Whitted,
        "path" => Mode::Path,
        other => return Err(format!("unknown render mode `{other}`")),
    };
    let tonemap =
        match render
            .word("tonemap")
            .unwrap_or(if mode == Mode::Path { "aces" } else { "clamp" })
        {
            "clamp" => Tonemap::Clamp,
            "reinhard" => Tonemap::Reinhard,
            "aces" => Tonemap::Aces,
            other => return Err(format!("unknown tonemap `{other}`")),
        };
    let frame = frame_override
        // The last top-level `frame` wins: `silicium-raytracer frames` appends one.
        .or_else(|| {
            root.iter()
                .rev()
                .find(|entry| entry.key.as_deref() == Some("frame"))
                .and_then(|entry| syntax::evaluate(&entry.value, 0.0))
        })
        .unwrap_or_else(|| render.number("frame", 0.0, 0.0));
    Ok(Settings {
        samples: render.number("samples", 1.0, frame).clamp(1.0, 65_536.0) as u32,
        mode,
        bounces: render
            .number("bounces", if mode == Mode::Path { 8.0 } else { 3.0 }, frame)
            .clamp(0.0, 64.0) as u32,
        exposure: render.number("exposure", 1.0, frame).max(0.0),
        tonemap,
        sky: render.number("sky", 1.0, frame).max(0.0),
        seed: render.number("seed", 0.0, frame).max(0.0) as u64,
        frame,
        clamp: render.number("clamp", 2.0, frame).max(0.0),
    })
}

/// Builds the scene of `text` at `frame` (the scene's own frame when `None`).
pub fn build(text: &str, frame_override: Option<f64>) -> Result<Scene, String> {
    let root = syntax::parse(text).map_err(|error| error.to_string())?;
    let settings = settings(&root, frame_override)?;
    let frame = settings.frame;
    let empty: Vec<Entry> = Vec::new();
    let camera_block = root.block("camera").unwrap_or(&empty);
    let resolution = camera_block.block("resolution").unwrap_or(&empty);
    let width = resolution.number("width", 320.0, 0.0).max(1.0) as usize;
    let height = resolution.number("height", 200.0, 0.0).max(1.0) as usize;

    let mut builder = Builder {
        frame,
        shapes: Vec::new(),
        shape_material: Vec::new(),
        materials: Vec::new(),
        named: HashMap::new(),
    };
    if let Some(materials) = root.block("materials") {
        for entry in materials.all("material") {
            for block in syntax::items(&entry.value) {
                let name = block
                    .word("name")
                    .ok_or_else(|| format!("line {}: material without `name`", entry.line))?;
                let parsed = material(block, 0.32, frame)?;
                builder.materials.push(parsed);
                builder
                    .named
                    .insert(name.to_string(), builder.materials.len() - 1);
            }
        }
    }
    if let Some(primitives) = root.block("primitives") {
        for entry in primitives {
            let Some(name) = entry.key.as_deref() else {
                continue;
            };
            for block in syntax::items(&entry.value) {
                builder.primitive(name, block, entry.line)?;
            }
        }
    }
    let mut points = Vec::new();
    let mut emitters = Vec::new();
    if let Some(lights) = root.block("lights") {
        let items = lights.iter().flat_map(|entry| {
            syntax::items(&entry.value)
                .into_iter()
                .map(move |block| (entry.key.as_deref(), block))
        });
        for (name, block) in items {
            let Some(name) = name else {
                continue;
            };
            let n = |key: &str, default: f64| block.number(key, default, frame);
            let position = Vec3::new(n("x", 4.0), n("y", 0.0), n("z", 5.0));
            let intensity = n("intensity", 450.0).max(0.0);
            let tint = color(block, 255.0, frame);
            match name {
                "point" => points.push(PointLight {
                    position,
                    intensity,
                    color: tint,
                }),
                "area" => {
                    let radius = n("radius", 0.5).max(EPSILON);
                    builder.materials.push(Material {
                        kind: MaterialKind::Emissive,
                        color: tint,
                        reflectivity: 0.0,
                        specular: 0.0,
                        shininess: 1.0,
                        roughness: 0.0,
                        ior: 1.0,
                        emission: tint * (intensity * LIGHT_UNIT / (radius * radius)),
                    });
                    let material = builder.materials.len() - 1;
                    builder.add(
                        Shape::Sphere {
                            center: position,
                            radius,
                        },
                        material,
                    );
                    emitters.push(Emitter {
                        shape: builder.shapes.len() - 1,
                        intensity: Some(intensity),
                        color: tint,
                    });
                }
                _ => {}
            }
        }
    }
    for (index, shape) in builder.shapes.iter().enumerate() {
        let material = &builder.materials[builder.shape_material[index]];
        let sampled = matches!(
            shape,
            Shape::Sphere { .. } | Shape::Quad { .. } | Shape::Triangle { .. }
        );
        if material.kind == MaterialKind::Emissive
            && sampled
            && !emitters.iter().any(|e: &Emitter| e.shape == index)
        {
            emitters.push(Emitter {
                shape: index,
                intensity: None,
                color: material.emission,
            });
        }
    }
    if settings.mode == Mode::Whitted
        && points.is_empty()
        && emitters.iter().all(|e| e.intensity.is_none())
    {
        // Default light, as in the first versions of the engine.
        points.push(PointLight {
            position: Vec3::new(4.0, 0.0, 5.0),
            intensity: 450.0,
            color: Vec3::new(1.0, 1.0, 1.0),
        });
    }
    let planes: Vec<usize> = (0..builder.shapes.len())
        .filter(|i| matches!(builder.shapes[*i], Shape::Plane { .. }))
        .collect();
    let finite: Vec<usize> = (0..builder.shapes.len())
        .filter(|i| !planes.contains(i))
        .collect();
    let bvh = Bvh::build(&builder.shapes, finite);
    Ok(Scene {
        width,
        height,
        camera: camera(camera_block, frame),
        settings,
        shapes: builder.shapes,
        shape_material: builder.shape_material,
        materials: builder.materials,
        planes,
        bvh,
        points,
        emitters,
    })
}
