//! Scene checker behind `silicium-raytracer check`: reports what in a `.cfg`
//! scene is wrong or silently ignored, with line numbers, before a job is sent.
//!
//! The parser ([`crate::parser`]) is tolerant on purpose: a misspelt key, a
//! value that is not a number or a feature the engine lacks are replaced by
//! defaults without a word. This module walks the same tokens as the parser,
//! against the schema the parser actually reads, and compares with what the
//! parser and the tile planner really end up using.
//!
//! The site runs the same rules in the browser (`FrontEnd/utils/sceneCheck.ts`);
//! `tests/fixtures/check_cases.json` is shared by both test suites.

use crate::{parser::parse_scene_text, pipeline::tiles::scene_resolution, EPSILON};
use serde::Serialize;
use std::collections::HashMap;

/// How bad an issue is: an `Error` makes the render differ from the file
/// (or the job fail); a `Warning` is probably not what the author meant.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Error,
    Warning,
}

/// One finding. `line` is 1-based, 0 for the whole scene.
#[derive(Clone, Debug, Serialize)]
pub struct Issue {
    pub severity: Severity,
    pub code: &'static str,
    pub line: usize,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub key: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub suggestion: Option<String>,
    pub message: String,
}

/// What the renderer will draw, as read by the parser.
#[derive(Clone, Debug, Serialize)]
pub struct Summary {
    pub width: usize,
    pub height: usize,
    pub spheres: usize,
    pub planes: usize,
    pub lights: usize,
    pub field_of_view: f64,
}

/// Result of [`check_scene`].
#[derive(Clone, Debug, Serialize)]
pub struct Report {
    pub valid: bool,
    pub errors: usize,
    pub warnings: usize,
    pub issues: Vec<Issue>,
    pub scene: Summary,
}

/// Words other raytracers accept and this one does not.
const UNSUPPORTED: &[&str] = &[
    "ambient",
    "antialiasing",
    "box",
    "cone",
    "cube",
    "cylinder",
    "diffuse",
    "directional",
    "mesh",
    "obj",
    "refraction",
    "scale",
    "shear",
    "spot",
    "texture",
    "torus",
    "translation",
    "transparency",
    "triangle",
];

/// Widest image the checker lets through without a warning (8K UHD).
const LARGE_PIXELS: usize = 7680 * 4320;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Kind {
    Root,
    Camera,
    Resolution,
    Position,
    Orientation,
    Primitives,
    Sphere,
    Plane,
    Color,
    Lights,
    Point,
    /// Content not read by the renderer (unknown or unsupported block).
    Skipped,
}

const MATERIAL: &[&str] = &[
    "reflection",
    "reflectivity",
    "specular",
    "shininess",
    "r",
    "g",
    "b",
];

fn values_of(kind: Kind) -> Vec<&'static str> {
    let mut keys: Vec<&'static str> = match kind {
        Kind::Camera => vec!["fieldOfView"],
        Kind::Resolution => vec!["width", "height"],
        Kind::Position | Kind::Orientation => vec!["x", "y", "z"],
        Kind::Sphere => vec!["x", "y", "z", "radius"],
        Kind::Plane => vec!["x", "y", "z", "normal_x", "normal_y", "normal_z"],
        Kind::Color => vec!["r", "g", "b"],
        Kind::Point => vec!["x", "y", "z", "intensity", "r", "g", "b"],
        _ => vec![],
    };
    if matches!(kind, Kind::Sphere | Kind::Plane) {
        keys.extend_from_slice(MATERIAL);
    }
    keys
}

fn blocks_of(kind: Kind) -> &'static [&'static str] {
    match kind {
        Kind::Root => &["camera", "primitives", "lights", "effects"],
        Kind::Camera => &["resolution", "position", "rotation", "direction"],
        Kind::Primitives => &["sphere", "plane"],
        Kind::Sphere | Kind::Plane | Kind::Point => &["color"],
        Kind::Lights => &["point"],
        _ => &[],
    }
}

fn block_kind(name: &str) -> Option<Kind> {
    Some(match name {
        "camera" => Kind::Camera,
        "resolution" => Kind::Resolution,
        "position" => Kind::Position,
        "rotation" | "direction" => Kind::Orientation,
        "primitives" => Kind::Primitives,
        "sphere" => Kind::Sphere,
        "plane" => Kind::Plane,
        "color" => Kind::Color,
        "lights" => Kind::Lights,
        "point" => Kind::Point,
        "effects" => Kind::Skipped,
        _ => return None,
    })
}

/// Valid range of a value, as `(min, max, parser clamps)`.
fn range_of(kind: Kind, key: &str) -> Option<(f64, f64)> {
    Some(match (kind, key) {
        (_, "reflection" | "reflectivity") => (0.0, 0.95),
        (_, "specular") => (0.0, 2.0),
        (_, "shininess") => (1.0, 512.0),
        (_, "r" | "g" | "b") => (0.0, 255.0),
        (Kind::Camera, "fieldOfView") => (1.0, 179.0),
        (Kind::Resolution, "width" | "height") => (1.0, f64::INFINITY),
        (Kind::Point, "intensity") => (0.0, f64::INFINITY),
        (Kind::Sphere, "radius") => (EPSILON, f64::INFINITY),
        _ => return None,
    })
}

struct Token {
    text: String,
    line: usize,
}

/// Same characters as the parser's tokenizer, without comments (`#`, `//`),
/// keeping line numbers. Also returns the lines whose comment holds a
/// `key = number` (the parser, which knows no comments, reads it).
fn tokenize(text: &str) -> (Vec<Token>, Vec<usize>) {
    let mut result = Vec::new();
    let mut commented = Vec::new();
    for (index, raw_line) in text.lines().enumerate() {
        let line = index + 1;
        let cut = [raw_line.find('#'), raw_line.find("//")]
            .into_iter()
            .flatten()
            .min();
        let (code, comment) = match cut {
            Some(position) => (&raw_line[..position], &raw_line[position..]),
            None => (raw_line, ""),
        };
        if has_assignment(comment) {
            commented.push(line);
        }
        let mut current = String::new();
        for character in code.chars() {
            if character.is_ascii_alphanumeric()
                || character == '_'
                || character == '.'
                || ((character == '-' || character == '+') && current.is_empty())
            {
                current.push(character);
            } else {
                if !current.is_empty() {
                    result.push(Token {
                        text: std::mem::take(&mut current),
                        line,
                    });
                }
                if "{}=:;".contains(character) {
                    result.push(Token {
                        text: character.to_string(),
                        line,
                    });
                }
            }
        }
        if !current.is_empty() {
            result.push(Token {
                text: current,
                line,
            });
        }
    }
    (result, commented)
}

/// `word = number` (a word starting with a letter) somewhere in `text`.
fn has_assignment(text: &str) -> bool {
    let bytes = text.as_bytes();
    bytes.iter().enumerate().any(|(index, &byte)| {
        if byte != b'=' {
            return false;
        }
        let before = text[..index].trim_end();
        let after = text[index + 1..].trim_start();
        let word: String = before
            .chars()
            .rev()
            .take_while(|c| c.is_ascii_alphanumeric() || *c == '_')
            .collect();
        word.chars().last().is_some_and(|c| c.is_ascii_alphabetic())
            && after
                .chars()
                .next()
                .is_some_and(|c| c.is_ascii_digit() || "-+.".contains(c))
    })
}

fn issue(severity: Severity, code: &'static str, line: usize, key: &str, message: &str) -> Issue {
    Issue {
        severity,
        code,
        line,
        key: key.to_string(),
        suggestion: None,
        message: message.to_string(),
    }
}

fn is_punctuation(text: &str) -> bool {
    matches!(text, "{" | "}" | "=" | ":" | ";")
}

/// Closest known word (case-insensitive edit distance at most 2).
fn suggest(word: &str, candidates: &[&str]) -> Option<String> {
    let lower = word.to_ascii_lowercase();
    candidates
        .iter()
        .map(|candidate| {
            (
                distance(&lower, &candidate.to_ascii_lowercase()),
                *candidate,
            )
        })
        .filter(|(score, candidate)| *score <= 2 && *score < candidate.len())
        .min_by_key(|(score, _)| *score)
        .map(|(_, candidate)| candidate.to_string())
}

fn distance(left: &str, right: &str) -> usize {
    let right: Vec<char> = right.chars().collect();
    let mut previous: Vec<usize> = (0..=right.len()).collect();
    for (i, a) in left.chars().enumerate() {
        let mut row = vec![i + 1];
        for (j, b) in right.iter().enumerate() {
            let cost = usize::from(a != *b);
            row.push(
                (previous[j] + cost)
                    .min(previous[j + 1] + 1)
                    .min(row[j] + 1),
            );
        }
        previous = row;
    }
    previous[right.len()]
}

struct Frame {
    kind: Kind,
    name: String,
    line: usize,
    values: HashMap<String, (f64, usize)>,
    /// Camera only: kind and line of the block holding the first `x`/`y`/`z`.
    first_coordinate: Option<(Kind, usize)>,
}

impl Frame {
    fn new(kind: Kind, name: &str, line: usize) -> Self {
        Frame {
            kind,
            name: name.to_string(),
            line,
            values: HashMap::new(),
            first_coordinate: None,
        }
    }
    fn value(&self, key: &str, default: f64) -> f64 {
        self.values
            .get(key)
            .map(|(value, _)| *value)
            .unwrap_or(default)
    }
}

#[derive(Default)]
struct Walk {
    issues: Vec<Issue>,
    resolution_line: Option<usize>,
    camera_line: Option<usize>,
    lights: usize,
    /// `(x + radius, line)` of each sphere, to compare with the camera.
    spheres: Vec<(f64, usize)>,
    /// First and last line of every block, to tell which comments the parser reads.
    spans: Vec<(usize, usize)>,
}

impl Walk {
    fn close(&mut self, frame: Frame, last_line: usize) {
        self.spans.push((frame.line, last_line));
        match frame.kind {
            Kind::Plane => {
                let normal = [
                    frame.value("normal_x", 0.0),
                    frame.value("normal_y", 0.0),
                    frame.value("normal_z", 1.0),
                ];
                if normal.iter().map(|v| v * v).sum::<f64>().sqrt() <= EPSILON {
                    self.issues.push(issue(
                        Severity::Error,
                        "zero_normal",
                        frame.line,
                        "",
                        "this plane's normal is (0, 0, 0): it will not be drawn",
                    ));
                }
            }
            Kind::Sphere => {
                self.spheres.push((
                    frame.value("x", 0.0) + frame.value("radius", 1.0),
                    frame.line,
                ));
            }
            Kind::Orientation => {
                let (x, y, z) = (
                    frame.value("x", 0.0),
                    frame.value("y", 0.0),
                    frame.value("z", 0.0),
                );
                let ignored = if frame.name == "rotation" {
                    x != 0.0 || y != 0.0 || z != 0.0
                } else {
                    y != 0.0 || z != 0.0 || x <= 0.0
                };
                if ignored {
                    self.issues.push(issue(
                        Severity::Warning,
                        "camera_orientation_ignored",
                        frame.line,
                        &frame.name,
                        "the camera always looks along +x: `rotation` and `direction` are ignored",
                    ));
                }
            }
            Kind::Camera => {
                if let Some((Kind::Orientation, line)) = frame.first_coordinate {
                    self.issues.push(issue(
                        Severity::Warning,
                        "camera_position_shadowed",
                        line,
                        "position",
                        "the renderer takes the first x/y/z of the camera as its position: write `position` first",
                    ));
                }
            }
            Kind::Resolution => {
                let (width, height) = (frame.value("width", 0.0), frame.value("height", 0.0));
                if width >= 1.0 && height >= 1.0 && width * height > LARGE_PIXELS as f64 {
                    self.issues.push(issue(
                        Severity::Warning,
                        "resolution_large",
                        frame.line,
                        "resolution",
                        "more than 8K: the render will be long and costly",
                    ));
                }
            }
            _ => {}
        }
    }

    fn assign(&mut self, stack: &mut [Frame], key: &str, value: &Token, line: usize) {
        let kind = stack.last().map(|frame| frame.kind).unwrap_or(Kind::Root);
        if kind == Kind::Skipped {
            return;
        }
        let known = values_of(kind);
        if !known.contains(&key) {
            if UNSUPPORTED.contains(&key) {
                self.issues.push(issue(
                    Severity::Warning,
                    "unsupported",
                    line,
                    key,
                    &format!("`{key}` is not supported by this renderer and is ignored"),
                ));
            } else {
                let mut candidates = known.clone();
                candidates.extend_from_slice(blocks_of(kind));
                let mut found = issue(
                    Severity::Warning,
                    "unknown_key",
                    line,
                    key,
                    &format!("unknown key `{key}`: it is ignored"),
                );
                found.suggestion = suggest(key, &candidates);
                self.issues.push(found);
            }
            return;
        }
        let Ok(number) = value.text.parse::<f64>() else {
            self.issues.push(issue(
                Severity::Error,
                "not_a_number",
                line,
                key,
                &format!(
                    "`{key}` must be a number, got `{}`: the default is used",
                    value.text
                ),
            ));
            return;
        };
        if kind == Kind::Sphere || kind == Kind::Plane {
            let other = match key {
                "reflection" => Some("reflectivity"),
                "reflectivity" => Some("reflection"),
                _ => None,
            };
            if other.is_some_and(|other| stack.last().is_some_and(|f| f.values.contains_key(other)))
            {
                self.issues.push(issue(
                    Severity::Warning,
                    "duplicate_reflection",
                    line,
                    key,
                    "`reflection` and `reflectivity` are the same setting: `reflectivity` wins",
                ));
            }
        }
        let frame = stack.last_mut().expect("root frame");
        if frame.values.contains_key(key) {
            self.issues.push(issue(
                Severity::Warning,
                "duplicate_key",
                line,
                key,
                &format!("`{key}` is given twice: only the first one is used"),
            ));
            return;
        }
        frame.values.insert(key.to_string(), (number, line));
        if let Some((min, max)) = range_of(kind, key) {
            if !(min..=max).contains(&number) {
                let bounds = if max.is_infinite() {
                    format!("at least {min}")
                } else {
                    format!("between {min} and {max}")
                };
                self.issues.push(issue(
                    Severity::Warning,
                    "out_of_range",
                    line,
                    key,
                    &format!("`{key}` should be {bounds}, got {number}"),
                ));
            }
        }
        if matches!(key, "x" | "y" | "z") {
            if let Some(camera) = stack.iter_mut().rev().find(|f| f.kind == Kind::Camera) {
                if camera.first_coordinate.is_none() {
                    camera.first_coordinate = Some((kind, line));
                }
            }
        }
    }
}

/// Checks the text of a scene file.
pub fn check_scene(text: &str) -> Report {
    let mut walk = Walk::default();
    let (tokens, commented) = tokenize(text);
    let mut stack = vec![Frame::new(Kind::Root, "", 0)];
    let mut index = 0;
    while index < tokens.len() {
        let token = &tokens[index];
        let next = tokens.get(index + 1).map(|t| t.text.as_str());
        let after = tokens.get(index + 2);
        if token.text == "}" {
            if stack.len() == 1 {
                walk.issues.push(issue(
                    Severity::Error,
                    "unbalanced_braces",
                    token.line,
                    "",
                    "this `}` closes nothing",
                ));
            } else {
                let frame = stack.pop().expect("frame");
                walk.close(frame, token.line);
            }
            index += 1;
            continue;
        }
        if is_punctuation(&token.text) {
            index += 1;
            continue;
        }
        let parent = stack.last().map(|frame| frame.kind).unwrap_or(Kind::Root);
        if matches!(next, Some("=" | ":")) && after.is_some_and(|t| t.text == "{") {
            let name = token.text.as_str();
            let kind = if parent == Kind::Skipped {
                Kind::Skipped
            } else if blocks_of(parent).contains(&name) {
                block_kind(name).unwrap_or(Kind::Skipped)
            } else if UNSUPPORTED.contains(&name) {
                walk.issues.push(issue(
                    Severity::Warning,
                    "unsupported",
                    token.line,
                    name,
                    &format!("`{name}` is not supported by this renderer and is ignored"),
                ));
                Kind::Skipped
            } else if let Some(kind @ (Kind::Sphere | Kind::Plane | Kind::Point)) = block_kind(name)
            {
                walk.issues.push(issue(
                    Severity::Warning,
                    "misplaced",
                    token.line,
                    name,
                    &format!(
                        "`{name}` belongs in `{}`",
                        if kind == Kind::Point {
                            "lights"
                        } else {
                            "primitives"
                        }
                    ),
                ));
                kind
            } else {
                let mut found = issue(
                    Severity::Warning,
                    "unknown_block",
                    token.line,
                    name,
                    &format!("unknown block `{name}`: it is ignored"),
                );
                found.suggestion = suggest(name, blocks_of(parent));
                walk.issues.push(found);
                Kind::Skipped
            };
            match kind {
                Kind::Resolution => {
                    walk.resolution_line = walk.resolution_line.or(Some(token.line))
                }
                Kind::Camera => walk.camera_line = walk.camera_line.or(Some(token.line)),
                Kind::Point => walk.lights += 1,
                _ => {}
            }
            stack.push(Frame::new(kind, name, token.line));
            index += 3;
            continue;
        }
        if let (Some(separator @ ("=" | ":")), Some(value)) = (next, after) {
            if !is_punctuation(&value.text) {
                if separator == ":" {
                    if parent != Kind::Skipped {
                        walk.issues.push(issue(
                            Severity::Error,
                            "use_equals",
                            token.line,
                            &token.text,
                            &format!(
                                "write `{} = {}`: the renderer only reads `=`",
                                token.text, value.text
                            ),
                        ));
                    }
                } else {
                    walk.assign(&mut stack, &token.text, value, token.line);
                }
                index += 3;
                continue;
            }
        }
        if parent != Kind::Skipped && token.text.parse::<f64>().is_err() {
            walk.issues.push(issue(
                Severity::Warning,
                "unexpected_token",
                token.line,
                &token.text,
                &format!(
                    "`{}` is not a `key = value` nor a block: it is ignored",
                    token.text
                ),
            ));
        }
        index += 1;
    }
    while stack.len() > 1 {
        let frame = stack.pop().expect("frame");
        walk.issues.push(issue(
            Severity::Error,
            "unbalanced_braces",
            frame.line,
            &frame.name,
            &format!("`{}` is opened here and never closed", frame.name),
        ));
        walk.close(frame, usize::MAX);
    }
    for line in commented {
        if walk
            .spans
            .iter()
            .any(|(first, last)| (*first..=*last).contains(&line))
        {
            walk.issues.push(issue(
                Severity::Warning,
                "comment_assignment",
                line,
                "",
                "the renderer does not know comments: it still reads the `key = value` written in this one",
            ));
        }
    }

    let scene = parse_scene_text(text);
    let planned = scene_resolution(text);
    match walk.resolution_line {
        None => walk.issues.push(issue(
            Severity::Error,
            "missing_resolution",
            walk.camera_line.unwrap_or(0),
            "resolution",
            "no `resolution = { width = W height = H }` in the camera: the tiles and the render would disagree",
        )),
        Some(line) if planned != (scene.width, scene.height) => walk.issues.push(issue(
            Severity::Error,
            "resolution_mismatch",
            line,
            "resolution",
            &format!(
                "the tiles would be cut for {}x{} but the image is {}x{}: write `resolution = {{ width = W height = H }}`, width first",
                planned.0, planned.1, scene.width, scene.height
            ),
        )),
        Some(_) => {}
    }
    let primitives = scene.primitives.len();
    if primitives == 0 {
        walk.issues.push(issue(
            Severity::Warning,
            "empty_scene",
            0,
            "",
            "no sphere nor plane: the image will only show the sky",
        ));
    }
    if walk.lights == 0 {
        walk.issues.push(issue(
            Severity::Warning,
            "no_light",
            0,
            "",
            "no light: a default white light at (4, 0, 5) is added",
        ));
    }
    for (front, line) in &walk.spheres {
        if *front <= scene.camera.x {
            walk.issues.push(issue(
                Severity::Warning,
                "behind_camera",
                *line,
                "x",
                "this sphere is behind the camera (the camera looks along +x): it will not be seen",
            ));
        }
    }

    walk.issues
        .sort_by_key(|issue| (issue.line == 0, issue.line));
    let errors = walk
        .issues
        .iter()
        .filter(|i| i.severity == Severity::Error)
        .count();
    let spheres = scene
        .primitives
        .iter()
        .filter(|p| matches!(p, crate::scene::Primitive::Sphere { .. }))
        .count();
    Report {
        valid: errors == 0,
        errors,
        warnings: walk.issues.len() - errors,
        issues: walk.issues,
        scene: Summary {
            width: scene.width,
            height: scene.height,
            spheres,
            planes: primitives - spheres,
            lights: scene.lights.len(),
            field_of_view: scene.fov,
        },
    }
}
