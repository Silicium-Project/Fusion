//! Scene commands: `check <scene.cfg>` (what in a scene file is wrong or
//! silently ignored), `version` (what this engine renders), `import-obj`
//! (a model as a `mesh` block) and `frames` (one scene file per frame).

use super::options::{read, write, Options};
use serde_json::{json, Value};
use silicium_raytracer::{
    check::check_scene,
    engine::{self, obj, syntax::BlockExt},
};
use std::path::Path;

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

/// `version`: `{engine, features}` of this binary.
pub fn version() -> Value {
    json!({
        "engine": engine::ENGINE_VERSION,
        "features": ["samples", "camera", "materials", "area_lights", "path_tracing", "meshes", "transforms", "animation"],
    })
}

/// `import-obj <model.obj> [--material NAME] [--fit SIZE] [--up y|z] [--output FILE]`:
/// the model as a `mesh` block (y-up models are turned z-up by default).
/// Prints `{vertices, triangles, path}` and the block itself when there is
/// no `--output`.
pub fn import_obj_command(options: &Options) -> Result<(Value, i32), String> {
    let input = options.input("model OBJ")?;
    let text = String::from_utf8_lossy(&read(input)?).into_owned();
    let mut model = obj::parse(&text)?;
    if options.one("up").unwrap_or("y") == "y" {
        model.y_up_to_z_up();
    }
    if let Some(size) = options.non_empty("fit") {
        model.fit(size.parse().map_err(|_| format!("invalid --fit: {size}"))?);
    }
    let name = Path::new(input)
        .file_name()
        .map_or(input.to_string(), |n| n.to_string_lossy().into_owned());
    let block = model.to_block(options.non_empty("material").unwrap_or("model"), &name);
    let mut payload = json!({"vertices": model.vertices.len(), "triangles": model.faces.len()});
    match options.non_empty("output") {
        Some(output) => {
            write(Path::new(output), block.as_bytes())?;
            payload["path"] = json!(output);
        }
        None => payload["block"] = json!(block),
    }
    Ok((payload, 0))
}

/// `frames <scene.cfg> --output-dir DIR [--first N] [--last N]`: writes one
/// scene file per frame of the animation (`animation = { frames = N }`),
/// each ending with `frame = N`. Each file is an ordinary job for the
/// network. Prints `{frames, files}`.
pub fn frames_command(options: &Options) -> Result<(Value, i32), String> {
    let input = options.input("scene")?;
    let text = String::from_utf8_lossy(&read(input)?).into_owned();
    let root = engine::syntax::parse(&text).map_err(|error| error.to_string())?;
    let count = root
        .block("animation")
        .map(|animation| animation.number("frames", 0.0, 0.0))
        .unwrap_or(0.0) as usize;
    if count == 0 {
        return Err("the scene has no `animation = { frames = N }`".into());
    }
    let first = options.number("first", 0)?;
    let last = options.number("last", count - 1)?.min(count - 1);
    let directory = options
        .non_empty("output-dir")
        .ok_or("missing --output-dir")?;
    let stem = Path::new(input)
        .file_stem()
        .map_or("scene".into(), |s| s.to_string_lossy().into_owned());
    let mut files = Vec::new();
    for frame in first..=last {
        let path = Path::new(directory).join(format!("{stem}-frame-{frame:04}.cfg"));
        let body = format!("{}\n\n# Frame {frame} of {count} (written by `silicium-raytracer frames`).\nframe = {frame}\n", text.trim_end());
        write(&path, body.as_bytes())?;
        files.push(path.display().to_string());
    }
    Ok((json!({"frames": files.len(), "files": files}), 0))
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

    #[test]
    fn frames_writes_one_scene_per_frame_and_import_obj_writes_a_mesh() {
        let scene = temp_file(
            "anim.cfg",
            b"render : { }\nanimation : { frames = 3 }\ncamera : { resolution = { width = 4 height = 4 } }\nprimitives : { sphere = { x = 5 y = { 0 = -1 2 = 1 } } }\n",
        );
        let directory =
            std::env::temp_dir().join(format!("silicium-frames-{}", std::process::id()));
        let (payload, code) = run(
            "frames",
            &args(&[&scene, "--output-dir", directory.to_str().unwrap()]),
        )
        .unwrap();
        assert_eq!((code, payload["frames"].as_u64()), (0, Some(3)));
        let last = std::fs::read_to_string(payload["files"][2].as_str().unwrap()).unwrap();
        assert!(last.trim_end().ends_with("frame = 2"));
        assert_eq!(
            silicium_raytracer::engine::scene::build(&last, None)
                .unwrap()
                .settings
                .frame,
            2.0
        );
        std::fs::remove_dir_all(directory).unwrap();

        let model = temp_file("model.obj", b"v 0 0 0\nv 1 0 0\nv 0 0 1\nf 1 2 3\n");
        let (payload, _) = run(
            "import-obj",
            &args(&[&model, "--material", "gold", "--fit", "2"]),
        )
        .unwrap();
        assert_eq!(payload["triangles"], 1);
        let block = payload["block"].as_str().unwrap();
        let text = format!("render : {{ }}\ncamera : {{ resolution = {{ width = 4 height = 4 }} }}\nmaterials : {{ material = {{ name = gold type = metal }} }}\nprimitives : {{\n{block}}}\n");
        assert!(silicium_raytracer::check::check_scene(&text).valid);

        let (payload, _) = run("version", &[]).unwrap();
        assert_eq!(payload["engine"], 2);
    }
}
