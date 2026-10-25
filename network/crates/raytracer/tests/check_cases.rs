//! Runs the scene checks of `tests/fixtures/check_cases.json` (shared with the
//! site's copy in `FrontEnd/tests/fixtures/`) and the shipped example scenes.

use serde_json::Value;
use silicium_raytracer::check::check_scene;

#[test]
fn shared_check_cases() {
    let cases: Value =
        serde_json::from_str(include_str!("fixtures/check_cases.json")).expect("valid fixture");
    for case in cases["cases"].as_array().expect("cases") {
        let name = case["name"].as_str().unwrap();
        let text = case["lines"]
            .as_array()
            .unwrap()
            .iter()
            .map(|line| line.as_str().unwrap())
            .collect::<Vec<_>>()
            .join("\n");
        let report = check_scene(&text);
        let mut got: Vec<String> = report
            .issues
            .iter()
            .map(|issue| format!("{}@{}", issue.code, issue.line))
            .collect();
        let mut expected: Vec<String> = case["expected"]
            .as_array()
            .unwrap()
            .iter()
            .map(|item| format!("{}@{}", item["code"].as_str().unwrap(), item["line"]))
            .collect();
        got.sort();
        expected.sort();
        assert_eq!(got, expected, "case `{name}`: {:#?}", report.issues);
        for item in case["expected"].as_array().unwrap() {
            let found = report
                .issues
                .iter()
                .find(|issue| {
                    issue.code == item["code"].as_str().unwrap()
                        && Some(issue.line as u64) == item["line"].as_u64()
                        && item["key"].as_str().is_none_or(|key| issue.key == key)
                })
                .unwrap_or_else(|| panic!("case `{name}`: no issue matching {item}"));
            if let Some(suggestion) = item["suggestion"].as_str() {
                assert_eq!(
                    found.suggestion.as_deref(),
                    Some(suggestion),
                    "case `{name}`"
                );
            }
        }
    }
}

#[test]
fn shipped_scenes_are_clean() {
    for (name, text) in [
        ("demo-scene", include_str!("../scenes/demo-scene.cfg")),
        (
            "silicium-test-scene",
            include_str!("../scenes/silicium-test-scene.cfg"),
        ),
        (
            "silicium-multi-fragment-scene",
            include_str!("../scenes/silicium-multi-fragment-scene.cfg"),
        ),
    ] {
        let report = check_scene(text);
        assert!(report.issues.is_empty(), "{name}: {:#?}", report.issues);
    }
}
