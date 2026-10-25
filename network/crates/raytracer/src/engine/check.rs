//! Rules of `check` (report types in `crate::check`), against the scene
//! format described in the README.

use super::{
    geometry::Shape,
    scene::{build, Mode},
    syntax::{self, BlockExt, Entry, Value},
    ENGINE_VERSION,
};
use crate::math::Vec3;
use crate::{
    check::{issue, report, suggest, Issue, Report, Severity, Summary, LARGE_PIXELS},
    pipeline::tiles::scene_resolution,
};
use std::collections::HashSet;

/// Words other raytracers accept and this one does not.
const UNSUPPORTED: &[&str] = &[
    "ambient",
    "antialiasing",
    "cone",
    "cube",
    "cylinder",
    "diffuse_light",
    "directional",
    "obj",
    "refraction",
    "shear",
    "spot",
    "texture",
    "torus",
    "transparency",
];

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Kind {
    Root,
    Render,
    Camera,
    Resolution,
    Vector,
    Color,
    Materials,
    Material,
    Primitives,
    Object(&'static str),
    Lights,
    Light(&'static str),
    Animation,
    List,
}

const MATERIAL_VALUES: &[&str] = &[
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

fn values(kind: Kind) -> Vec<&'static str> {
    let mut list: Vec<&'static str> = match kind {
        Kind::Root => vec!["frame"],
        Kind::Render => vec![
            "engine", "samples", "bounces", "exposure", "sky", "seed", "frame", "clamp",
        ],
        Kind::Camera => vec!["fieldOfView", "aperture", "focus_distance", "x", "y", "z"],
        Kind::Resolution => vec!["width", "height"],
        Kind::Vector => vec!["x", "y", "z"],
        Kind::Color => vec!["r", "g", "b"],
        Kind::Material => MATERIAL_VALUES.to_vec(),
        Kind::Object(shape) => {
            let mut own = match shape {
                "sphere" => vec!["x", "y", "z", "radius"],
                "plane" => vec!["x", "y", "z", "normal_x", "normal_y", "normal_z"],
                _ => vec![],
            };
            own.extend_from_slice(MATERIAL_VALUES);
            own
        }
        Kind::Light(shape) => {
            let mut own = vec!["x", "y", "z", "intensity", "r", "g", "b"];
            if shape == "area" {
                own.push("radius");
            }
            own
        }
        Kind::Animation => vec!["frames", "fps"],
        _ => vec![],
    };
    if matches!(kind, Kind::Object(_)) {
        list.push("scale");
    }
    list
}

/// Allowed words: (key, allowed values; empty = any word).
fn words(kind: Kind) -> &'static [(&'static str, &'static [&'static str])] {
    const TYPES: &[&str] = &["phong", "diffuse", "metal", "glass", "emissive"];
    match kind {
        Kind::Render => &[
            ("mode", &["whitted", "path"]),
            ("tonemap", &["clamp", "reinhard", "aces"]),
        ],
        Kind::Material => &[("name", &[]), ("type", TYPES)],
        Kind::Object(_) => &[("material", &[]), ("type", TYPES)],
        _ => &[],
    }
}

fn blocks(kind: Kind) -> Vec<(&'static str, Kind)> {
    let transforms = [
        ("translate", Kind::Vector),
        ("rotate", Kind::Vector),
        ("scale", Kind::Vector),
        ("color", Kind::Color),
    ];
    let mut list = match kind {
        Kind::Root => vec![
            ("render", Kind::Render),
            ("camera", Kind::Camera),
            ("materials", Kind::Materials),
            ("primitives", Kind::Primitives),
            ("lights", Kind::Lights),
            ("animation", Kind::Animation),
            // Empty in older example scenes; nothing is read from it.
            ("effects", Kind::List),
        ],
        Kind::Camera => vec![
            ("resolution", Kind::Resolution),
            ("position", Kind::Vector),
            ("look_at", Kind::Vector),
            ("direction", Kind::Vector),
            ("rotation", Kind::Vector),
            ("up", Kind::Vector),
        ],
        Kind::Materials => vec![("material", Kind::Material)],
        Kind::Material => vec![("color", Kind::Color)],
        Kind::Primitives => ["sphere", "plane", "box", "triangle", "quad", "mesh"]
            .map(|s| (s, Kind::Object(s)))
            .to_vec(),
        Kind::Object(shape) => {
            let mut own = match shape {
                "plane" => vec![("normal", Kind::Vector)],
                "box" => vec![("min", Kind::Vector), ("max", Kind::Vector)],
                "triangle" => vec![
                    ("a", Kind::Vector),
                    ("b", Kind::Vector),
                    ("c", Kind::Vector),
                ],
                "quad" => vec![
                    ("corner", Kind::Vector),
                    ("u", Kind::Vector),
                    ("v", Kind::Vector),
                ],
                "mesh" => vec![("vertices", Kind::List), ("faces", Kind::List)],
                _ => vec![],
            };
            own.extend_from_slice(&transforms);
            own
        }
        Kind::Lights => vec![
            ("point", Kind::Light("point")),
            ("area", Kind::Light("area")),
        ],
        Kind::Light(_) => vec![("color", Kind::Color)],
        _ => vec![],
    };
    list.dedup();
    list
}

fn range(kind: Kind, key: &str) -> Option<(f64, f64)> {
    Some(match (kind, key) {
        (Kind::Render, "samples") => (1.0, 65_536.0),
        (Kind::Render, "bounces") => (0.0, 64.0),
        (Kind::Render, "exposure" | "sky" | "seed" | "clamp") => (0.0, f64::INFINITY),
        (Kind::Render, "engine") => (1.0, f64::from(ENGINE_VERSION)),
        (Kind::Camera, "fieldOfView") => (1.0, 179.0),
        (Kind::Camera, "aperture") => (0.0, f64::INFINITY),
        (Kind::Resolution, _) => (1.0, f64::INFINITY),
        (Kind::Color, _) | (_, "r" | "g" | "b") => (0.0, 255.0),
        (_, "reflection" | "reflectivity") => (0.0, 0.95),
        (_, "specular") => (0.0, 2.0),
        (_, "shininess") => (1.0, 512.0),
        (_, "roughness") => (0.0, 1.0),
        (_, "ior") => (1.0, 3.0),
        (_, "strength" | "intensity") => (0.0, f64::INFINITY),
        (_, "radius") => (1e-4, f64::INFINITY),
        _ => return None,
    })
}

struct Walk {
    issues: Vec<Issue>,
    material_names: HashSet<String>,
    material_uses: Vec<(String, usize)>,
    lights: usize,
    resolution_line: Option<usize>,
    camera_line: Option<usize>,
    /// Centre, radius and line of each sphere (transforms other than
    /// `translate` and `scale` ignored), to warn about spheres behind the camera.
    spheres: Vec<(Vec3, f64, usize)>,
}

impl Walk {
    fn push(
        &mut self,
        severity: Severity,
        code: &'static str,
        line: usize,
        key: &str,
        message: String,
        suggestion: Option<String>,
    ) {
        let mut found = issue(severity, code, line, key, &message);
        found.suggestion = suggestion;
        self.issues.push(found);
    }

    fn number(&mut self, kind: Kind, key: &str, entry: &Entry) {
        let ok = match &entry.value {
            Value::Number(value) => {
                if let Some((min, max)) = range(kind, key) {
                    if !(min..=max).contains(value) {
                        let bounds = if max.is_infinite() {
                            format!("at least {min}")
                        } else {
                            format!("between {min} and {max}")
                        };
                        self.push(
                            Severity::Warning,
                            "out_of_range",
                            entry.line,
                            key,
                            format!("`{key}` should be {bounds}, got {value}"),
                            None,
                        );
                    }
                }
                true
            }
            Value::Block(inner) => syntax::keyframes(inner).is_some(),
            Value::Word(_) => false,
        };
        if !ok {
            self.push(
                Severity::Error,
                "not_a_number",
                entry.line,
                key,
                format!("`{key}` must be a number or keyframes `{{ 0 = 1  24 = 2 }}`"),
                None,
            );
        }
    }

    fn block(&mut self, kind: Kind, entries: &[Entry]) {
        let numbers = values(kind);
        let allowed_words = words(kind);
        let children = blocks(kind);
        let mut seen = HashSet::new();
        if matches!(kind, Kind::Vector | Kind::Color) && entries.iter().all(|e| e.key.is_none()) {
            if entries.len() != 3 || entries.iter().any(|e| !matches!(e.value, Value::Number(_))) {
                let line = entries.first().map_or(0, |e| e.line);
                self.push(
                    Severity::Error,
                    "not_a_number",
                    line,
                    "",
                    "write three numbers or `x = … y = … z = …`".into(),
                    None,
                );
            }
            return;
        }
        if kind == Kind::List {
            return;
        }
        for entry in entries {
            let Some(key) = entry.key.as_deref() else {
                if kind != Kind::Root || !matches!(entry.value, Value::Block(_)) {
                    self.push(
                        Severity::Warning,
                        "unexpected_token",
                        entry.line,
                        "",
                        "a value without a key is ignored".into(),
                        None,
                    );
                }
                continue;
            };
            let block_kind = children
                .iter()
                .find(|(name, _)| *name == key)
                .map(|(_, k)| *k);
            let repeatable = matches!(
                block_kind,
                Some(Kind::Object(_) | Kind::Light(_) | Kind::Material)
            );
            if !repeatable && !seen.insert(key.to_string()) {
                self.push(
                    Severity::Warning,
                    "duplicate_key",
                    entry.line,
                    key,
                    format!("`{key}` is given twice: only the first one is used"),
                    None,
                );
                continue;
            }
            match (&entry.value, block_kind) {
                (Value::Block(inner), Some(child))
                    if !(key == "scale" && syntax::keyframes(inner).is_some()) =>
                {
                    match child {
                        Kind::Resolution => {
                            self.resolution_line = self.resolution_line.or(Some(entry.line))
                        }
                        Kind::Camera => self.camera_line = self.camera_line.or(Some(entry.line)),
                        _ => {}
                    }
                    // `point = ( { ... }, { ... } )`: one item per block of the list.
                    let parts = if repeatable {
                        syntax::items(&entry.value)
                    } else {
                        vec![inner.as_slice()]
                    };
                    for part in parts {
                        if matches!(child, Kind::Light(_)) {
                            self.lights += 1;
                        }
                        self.block(child, part);
                        if let Kind::Object(shape) = child {
                            self.object(shape, part, entry.line);
                        }
                        if matches!(child, Kind::Object(_) | Kind::Material) {
                            self.reflection_twice(part, entry.line);
                        }
                    }
                }
                _ if numbers.contains(&key) => self.number(kind, key, entry),
                (value, _) if allowed_words.iter().any(|(name, _)| *name == key) => {
                    let allowed = allowed_words
                        .iter()
                        .find(|(name, _)| *name == key)
                        .map(|(_, a)| *a)
                        .unwrap_or(&[]);
                    match value {
                        Value::Word(word) => {
                            if !allowed.is_empty() && !allowed.contains(&word.as_str()) {
                                self.push(
                                    Severity::Error,
                                    "invalid_value",
                                    entry.line,
                                    key,
                                    format!("`{key}` can be {}, not `{word}`", allowed.join(", ")),
                                    suggest(word, allowed),
                                );
                            }
                            if key == "name" && kind == Kind::Material {
                                self.material_names.insert(word.clone());
                            }
                            if key == "material" && matches!(kind, Kind::Object(_)) {
                                self.material_uses.push((word.clone(), entry.line));
                            }
                        }
                        _ => self.push(
                            Severity::Error,
                            "invalid_value",
                            entry.line,
                            key,
                            format!("`{key}` must be a word"),
                            None,
                        ),
                    }
                }
                (Value::Block(_), None) | (_, Some(_)) => {
                    let candidates: Vec<&str> = children.iter().map(|(name, _)| *name).collect();
                    if UNSUPPORTED.contains(&key) {
                        self.push(
                            Severity::Warning,
                            "unsupported",
                            entry.line,
                            key,
                            format!("`{key}` is not supported by this renderer"),
                            None,
                        );
                    } else if let Some((_, place)) = misplaced(key) {
                        self.push(
                            Severity::Warning,
                            "misplaced",
                            entry.line,
                            key,
                            format!("`{key}` belongs in `{place}`"),
                            None,
                        );
                    } else {
                        self.push(
                            Severity::Warning,
                            "unknown_block",
                            entry.line,
                            key,
                            format!("unknown block `{key}`: it is ignored"),
                            suggest(key, &candidates),
                        );
                    }
                }
                _ => {
                    let mut candidates: Vec<&str> = numbers.clone();
                    candidates.extend(allowed_words.iter().map(|(name, _)| *name));
                    candidates.extend(children.iter().map(|(name, _)| *name));
                    if UNSUPPORTED.contains(&key) {
                        self.push(
                            Severity::Warning,
                            "unsupported",
                            entry.line,
                            key,
                            format!("`{key}` is not supported by this renderer"),
                            None,
                        );
                    } else {
                        self.push(
                            Severity::Warning,
                            "unknown_key",
                            entry.line,
                            key,
                            format!("unknown key `{key}`: it is ignored"),
                            suggest(key, &candidates),
                        );
                    }
                }
            }
        }
    }

    fn reflection_twice(&mut self, entries: &[Entry], line: usize) {
        if entries.entry("reflection").is_some() && entries.entry("reflectivity").is_some() {
            self.push(
                Severity::Warning,
                "duplicate_reflection",
                line,
                "reflectivity",
                "`reflection` and `reflectivity` are the same setting: `reflectivity` wins".into(),
                None,
            );
        }
    }

    fn object(&mut self, shape: &str, entries: &[Entry], line: usize) {
        let n = |key: &str, default: f64| entries.number(key, default, 0.0);
        let offset = entries.block("translate").map_or(Vec3::default(), |t| {
            Vec3::new(
                t.number("x", 0.0, 0.0),
                t.number("y", 0.0, 0.0),
                t.number("z", 0.0, 0.0),
            )
        });
        let scale = match entries.entry("scale").map(|e| &e.value) {
            Some(Value::Number(s)) => s.abs(),
            Some(Value::Block(b)) if syntax::keyframes(b).is_none() => ["x", "y", "z"]
                .iter()
                .map(|k| b.number(k, 1.0, 0.0).abs())
                .fold(0.0, f64::max),
            _ => 1.0,
        };
        if shape == "sphere" {
            let centre = Vec3::new(n("x", 0.0), n("y", 0.0), n("z", 0.0)) + offset;
            self.spheres.push((centre, n("radius", 1.0) * scale, line));
        }
        if shape == "plane" {
            let normal = match entries.block("normal") {
                Some(b) => Vec3::new(
                    b.number("x", 0.0, 0.0),
                    b.number("y", 0.0, 0.0),
                    b.number("z", 1.0, 0.0),
                ),
                None => Vec3::new(n("normal_x", 0.0), n("normal_y", 0.0), n("normal_z", 1.0)),
            };
            if normal.length() <= crate::EPSILON {
                self.push(
                    Severity::Error,
                    "zero_normal",
                    line,
                    "",
                    "this plane's normal is (0, 0, 0): it cannot be drawn".into(),
                    None,
                );
            }
        }
        if shape != "mesh" {
            return;
        }
        let vertices = entries
            .block("vertices")
            .map(|v| v.numbers())
            .unwrap_or_default();
        let faces = entries
            .block("faces")
            .map(|f| f.numbers())
            .unwrap_or_default();
        let count = vertices.len() / 3;
        let problem = if !vertices.len().is_multiple_of(3) {
            Some("the number of vertex coordinates is not a multiple of 3".to_string())
        } else if !faces.len().is_multiple_of(3) || faces.is_empty() {
            Some("faces must be groups of 3 vertex numbers".to_string())
        } else {
            faces
                .iter()
                .find(|index| **index < 0.0 || index.fract() != 0.0 || **index as usize >= count)
                .map(|index| {
                    format!("a face uses vertex {index}, the mesh has {count} (numbered from 0)")
                })
        };
        if let Some(message) = problem {
            self.push(Severity::Error, "bad_mesh", line, "mesh", message, None);
        }
    }
}

fn misplaced(key: &str) -> Option<(&str, &str)> {
    match key {
        "sphere" | "plane" | "box" | "triangle" | "quad" | "mesh" => Some((key, "primitives")),
        "point" | "area" => Some((key, "lights")),
        "material" => Some((key, "materials")),
        _ => None,
    }
}

/// Checks a scene.
pub fn check(text: &str) -> Report {
    let mut summary = Summary {
        width: 320,
        height: 200,
        spheres: 0,
        planes: 0,
        lights: 0,
        field_of_view: 55.0,
        engine: 2,
        triangles: 0,
        samples: 1,
        mode: "whitted",
    };
    let root = match syntax::parse(text) {
        Ok(root) => root,
        Err(error) => {
            let found = issue(Severity::Error, error.code, error.line, "", &error.message);
            return report(vec![found], summary);
        }
    };
    let mut walk = Walk {
        issues: Vec::new(),
        material_names: HashSet::new(),
        material_uses: Vec::new(),
        lights: 0,
        resolution_line: None,
        camera_line: None,
        spheres: Vec::new(),
    };
    walk.block(Kind::Root, &root);
    let uses = std::mem::take(&mut walk.material_uses);
    let names: Vec<String> = walk.material_names.iter().cloned().collect();
    let candidates: Vec<&str> = names.iter().map(String::as_str).collect();
    for (name, line) in uses {
        if !walk.material_names.contains(&name) {
            walk.push(
                Severity::Error,
                "unknown_material",
                line,
                &name,
                format!("no material named `{name}` in `materials`"),
                suggest(&name, &candidates),
            );
        }
    }
    if let Some(engine) = root
        .block("render")
        .and_then(|r| r.entry("engine"))
        .and_then(|e| syntax::evaluate(&e.value, 0.0))
    {
        if engine > f64::from(ENGINE_VERSION) {
            let line = root
                .block("render")
                .and_then(|r| r.entry("engine"))
                .map_or(0, |e| e.line);
            walk.push(
                Severity::Error,
                "engine_too_new",
                line,
                "engine",
                format!("the scene needs engine {engine}, this one is {ENGINE_VERSION}"),
                None,
            );
        }
    }

    match build(text, None) {
        Ok(scene) => {
            let camera = scene.camera;
            for (centre, radius, line) in std::mem::take(&mut walk.spheres) {
                if (centre - camera.origin).dot(camera.forward) + radius <= 0.0 {
                    walk.push(
                        Severity::Warning,
                        "behind_camera",
                        line,
                        "x",
                        "this sphere is behind the camera: it will not be seen".into(),
                        None,
                    );
                }
            }
            let planned = scene_resolution(text);
            match walk.resolution_line {
                None => walk.push(Severity::Error, "missing_resolution", walk.camera_line.unwrap_or(0), "resolution", "no `resolution = { width = W height = H }` in the camera".into(), None),
                Some(line) if planned != (scene.width, scene.height) => walk.push(
                    Severity::Error,
                    "resolution_mismatch",
                    line,
                    "resolution",
                    format!("the tiles would be cut for {}x{} but the image is {}x{}: write `resolution = {{ width = W height = H }}`, width first", planned.0, planned.1, scene.width, scene.height),
                    None,
                ),
                Some(line) => {
                    let pixels = scene.width * scene.height;
                    if pixels > LARGE_PIXELS {
                        walk.push(Severity::Warning, "resolution_large", line, "resolution", "more than 8K: the render will be long and costly".into(), None);
                    }
                }
            }
            let emitting = scene.emitters.len();
            let lit = !scene.points.is_empty()
                || emitting > 0
                || (scene.settings.mode == Mode::Path && scene.settings.sky > 0.0);
            if scene.shapes.len()
                == scene
                    .emitters
                    .iter()
                    .filter(|e| e.intensity.is_some())
                    .count()
            {
                walk.push(
                    Severity::Warning,
                    "empty_scene",
                    0,
                    "",
                    "no object: the image will only show the sky".into(),
                    None,
                );
            }
            if walk.lights == 0 && !lit {
                walk.push(
                    Severity::Warning,
                    "dark_scene",
                    0,
                    "",
                    "no light, no glowing object and no sky: the image will be black".into(),
                    None,
                );
            } else if walk.lights == 0 && scene.settings.mode == Mode::Whitted && emitting == 0 {
                walk.push(
                    Severity::Warning,
                    "no_light",
                    0,
                    "",
                    "no light: a default white light at (4, 0, 5) is added".into(),
                    None,
                );
            }
            summary.width = scene.width;
            summary.height = scene.height;
            summary.spheres = scene
                .shapes
                .iter()
                .enumerate()
                .filter(|(i, s)| {
                    matches!(s, Shape::Sphere { .. })
                        && !scene
                            .emitters
                            .iter()
                            .any(|e| e.shape == *i && e.intensity.is_some())
                })
                .count();
            summary.planes = scene.planes.len();
            summary.triangles = scene
                .shapes
                .iter()
                .filter(|s| matches!(s, Shape::Triangle { .. } | Shape::Quad { .. }))
                .count();
            summary.lights = scene.points.len() + scene.emitters.len();
            summary.samples = scene.settings.samples;
            summary.mode = if scene.settings.mode == Mode::Path {
                "path"
            } else {
                "whitted"
            };
            summary.field_of_view = root
                .block("camera")
                .map_or(55.0, |c| c.number("fieldOfView", 55.0, 0.0));
        }
        Err(error) => {
            if !walk.issues.iter().any(|i| i.severity == Severity::Error) {
                walk.push(Severity::Error, "engine_error", 0, "", error, None);
            }
        }
    }
    report(walk.issues, summary)
}
