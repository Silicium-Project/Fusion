//! `check <scene.cfg>`: what in a scene file is wrong or silently ignored.

use super::options::{read, Options};
use serde_json::Value;
use silicium_raytracer::check::check_scene;

/// Prints the [`silicium_raytracer::check::Report`] of the scene: `{valid,
/// errors, warnings, issues: [{severity, code, line, key, suggestion,
/// message}], scene: {width, height, spheres, planes, lights, field_of_view}}`.
/// Exit code 2 when the scene has errors (it would not render as written).
pub fn check_command(options: &Options) -> Result<(Value, i32), String> {
    let text = read(options.input("scene")?)?;
    let report = check_scene(&String::from_utf8_lossy(&text));
    let code = if report.valid { 0 } else { 2 };
    Ok((
        serde_json::to_value(report).map_err(|error| error.to_string())?,
        code,
    ))
}

#[cfg(test)]
mod tests {
    use super::super::run;
    use super::super::tests_support::{args, temp_file};

    #[test]
    fn check_reports_a_typo_with_its_line_and_fails_on_errors() {
        let ok = temp_file(
            "check-ok.cfg",
            b"camera : {\n resolution = { width = 8 height = 4 }\n};\nprimitives : {\n sphere = { x = 5 radus = 1 }\n};\nlights : { point = { x = 1 } };",
        );
        let (payload, code) = run("check", &args(&[&ok])).unwrap();
        assert_eq!(code, 0);
        assert_eq!(payload["issues"][0]["code"], "unknown_key");
        assert_eq!(payload["issues"][0]["line"], 5);
        assert_eq!(payload["issues"][0]["suggestion"], "radius");

        let bad = temp_file("check-bad.cfg", b"camera : { };");
        let (payload, code) = run("check", &args(&[&bad])).unwrap();
        assert_eq!(code, 2);
        assert_eq!(payload["valid"], false);
    }
}
