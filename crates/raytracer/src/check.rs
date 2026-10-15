//! Scene checker behind `silicium-raytracer check`: reports what in a `.cfg`
//! scene is wrong or silently ignored, with line numbers, before a job is
//! sent. The rules are in [`crate::engine::check`]; this module holds the
//! report types.
//!
//! The site runs the same rules in the browser (`FrontEnd/utils/sceneCheck.ts`);
//! `tests/fixtures/check_cases.json` is shared by both test suites.

use serde::Serialize;

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

/// What the engine will draw.
#[derive(Clone, Debug, Serialize)]
pub struct Summary {
    pub width: usize,
    pub height: usize,
    pub spheres: usize,
    pub planes: usize,
    pub lights: usize,
    pub field_of_view: f64,
    /// Version of the engine that checked the scene.
    pub engine: u32,
    /// Triangles and quads (boxes, meshes…).
    pub triangles: usize,
    /// Rays per pixel.
    pub samples: u32,
    /// `whitted` (classic lighting) or `path` (path tracing).
    pub mode: &'static str,
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

/// Widest image the checker lets through without a warning (8K UHD).
pub(crate) const LARGE_PIXELS: usize = 7680 * 4320;

/// An issue without suggestion.
pub(crate) fn issue(
    severity: Severity,
    code: &'static str,
    line: usize,
    key: &str,
    message: &str,
) -> Issue {
    Issue {
        severity,
        code,
        line,
        key: key.to_string(),
        suggestion: None,
        message: message.to_string(),
    }
}

/// Closest known word (case-insensitive edit distance at most 2).
pub(crate) fn suggest(word: &str, candidates: &[&str]) -> Option<String> {
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

/// Checks the text of a scene file.
pub fn check_scene(text: &str) -> Report {
    crate::engine::check::check(text)
}

/// Builds a report from its issues.
pub(crate) fn report(mut issues: Vec<Issue>, scene: Summary) -> Report {
    issues.sort_by_key(|issue| (issue.line == 0, issue.line));
    let errors = issues
        .iter()
        .filter(|i| i.severity == Severity::Error)
        .count();
    Report {
        valid: errors == 0,
        errors,
        warnings: issues.len() - errors,
        issues,
        scene,
    }
}
