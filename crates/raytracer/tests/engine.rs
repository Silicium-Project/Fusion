//! The engine must stay usable by the network: deterministic pixels whatever
//! the thread count or the tile, and pinned outputs so that a change of the
//! pixels (which would make nodes of different versions disagree) is a
//! deliberate one.

use silicium_raytracer::{
    check::check_scene,
    engine::{self, scene::build},
    pipeline::sha256_hex,
    render::RenderOptions,
};
use std::sync::Arc;

const DEMO: &str = include_str!("../scenes/demo-scene.cfg");

fn small_demo() -> String {
    DEMO.replace("width = 320 height = 200", "width = 48 height = 30")
}

fn render_scene(text: &str, options: RenderOptions) -> Vec<u8> {
    engine::render(Arc::new(build(text, None).expect("valid scene")), &options).0
}

const PATH_SCENE: &str = "render : { mode = path samples = 4 bounces = 4 }
camera : {
  resolution = { width = 32 height = 20 }
  position = { x = 0 y = 0 z = 0.5 }
  look_at = { x = 5 y = 0 z = 0 }
  fieldOfView = 50
}
materials : {
  material = { name = glass type = glass ior = 1.5 }
  material = { name = lamp type = emissive strength = 4 }
}
primitives : {
  plane = { z = -1 type = diffuse }
  sphere = { x = 5 y = 0.8 z = 0 radius = 0.8 material = glass }
  box = { translate = { x = 6 y = -1.2 z = -0.5 } rotate = { z = 25 } type = metal roughness = 0.2 }
  quad = { corner = { x = 4 y = -1 z = 3 } u = { x = 1 y = 0 z = 0 } v = { x = 0 y = 2 z = 0 } material = lamp }
}
lights : { area = { x = 2 y = -3 z = 3 radius = 0.3 intensity = 300 } }
";

#[test]
fn scenes_without_render_block_are_pinned() {
    // The classic look (one ray per pixel, Whitted lighting) of the demo scene.
    let pixels = render_scene(&small_demo(), RenderOptions::default());
    assert_eq!(sha256_hex(&pixels), PINNED_DEMO_HASH);
}

const PINNED_DEMO_HASH: &str = "514b05b3b50f59436fb8a8f68c2ea2fbbfc2e6d7369a646ffb54f40180f9db8f";

#[test]
fn a_tile_is_the_same_region_of_the_full_image_whatever_the_threads() {
    let full = render_scene(
        PATH_SCENE,
        RenderOptions {
            threads: Some(1),
            ..RenderOptions::default()
        },
    );
    let tile = render_scene(
        PATH_SCENE,
        RenderOptions {
            x_start: Some(5),
            x_end: Some(19),
            y_start: Some(3),
            y_end: Some(14),
            threads: Some(3),
            ..RenderOptions::default()
        },
    );
    let mut expected = Vec::new();
    for y in 3..14 {
        expected.extend_from_slice(&full[(y * 32 + 5) * 3..(y * 32 + 19) * 3]);
    }
    assert_eq!(tile, expected);
    let again = render_scene(
        PATH_SCENE,
        RenderOptions {
            threads: Some(4),
            ..RenderOptions::default()
        },
    );
    assert_eq!(full, again);
}

#[test]
fn engine_2_output_is_pinned() {
    // Changing this hash changes the pixels: nodes of different versions
    // would then reject each other's tiles. Do it only with a new
    // `ENGINE_VERSION`.
    let pixels = render_scene(PATH_SCENE, RenderOptions::default());
    assert_eq!(sha256_hex(&pixels), PINNED_PATH_HASH);
}

const PINNED_PATH_HASH: &str = "138b6ed2add7e56c7a46f6b6b80f03810a54c4ec6cafc6f00c399e739a8e1f19";

#[test]
fn several_samples_smooth_the_edges() {
    let one = render_scene(
        &format!("render : {{ samples = 1 }}\n{}", small_demo()),
        RenderOptions::default(),
    );
    let many = render_scene(
        &format!("render : {{ samples = 16 }}\n{}", small_demo()),
        RenderOptions::default(),
    );
    assert_ne!(one, many);
    // Averaged edge pixels take values between the two sides: the jumps
    // between neighbouring pixels get smaller overall.
    let jumps = |pixels: &[u8]| -> u64 {
        pixels
            .chunks(48 * 3)
            .flat_map(|row| row.windows(4).map(|w| u64::from(w[0].abs_diff(w[3]))))
            .sum()
    };
    assert!(
        jumps(&many) < jumps(&one),
        "{} vs {}",
        jumps(&many),
        jumps(&one)
    );
}

#[test]
fn look_at_the_default_direction_changes_nothing() {
    let base = format!("render : {{ }}\n{}", small_demo());
    let aimed = base.replace(
        "fieldOfView = 55.0",
        "fieldOfView = 55.0\n\tlook_at = { x = 9 y = 0 z = 0 }",
    );
    assert_ne!(base, aimed);
    let a = render_scene(&base, RenderOptions::default());
    let b = render_scene(&aimed, RenderOptions::default());
    let worst = a.iter().zip(&b).map(|(x, y)| x.abs_diff(*y)).max().unwrap();
    assert!(worst <= 1);
}

#[test]
fn keyframes_move_objects_between_frames() {
    let text = "render : { }\ncamera : { resolution = { width = 24 height = 16 } }\n\
                primitives : { sphere = { x = 5 y = { 0 = -2  10 = 2 } radius = 0.8 } }";
    let at = |frame| {
        let scene = build(text, Some(frame)).unwrap();
        match scene.shapes[0] {
            engine::geometry::Shape::Sphere { center, .. } => center.y,
            _ => unreachable!(),
        }
    };
    assert_eq!(
        (at(0.0), at(5.0), at(10.0), at(20.0)),
        (-2.0, 0.0, 2.0, 2.0)
    );
    // The last top-level `frame` wins (what `frames` appends).
    assert_eq!(
        build(&format!("{text}\nframe = 0\nframe = 10"), None)
            .unwrap()
            .settings
            .frame,
        10.0
    );
}

#[test]
fn a_newer_engine_is_refused_instead_of_drawn_differently() {
    let error = build("render : { engine = 3 }", None).unwrap_err();
    assert!(error.starts_with("scene_requires_engine:3"));
    let report =
        check_scene("render : { engine = 3 }\ncamera : { resolution = { width = 4 height = 4 } }");
    assert!(report.issues.iter().any(|i| i.code == "engine_too_new"));
}

#[test]
fn check_understands_the_scene_format() {
    let codes = |text: &str| {
        check_scene(text)
            .issues
            .iter()
            .map(|i| {
                format!(
                    "{}@{}{}",
                    i.code,
                    i.line,
                    i.suggestion
                        .as_deref()
                        .map(|s| format!(">{s}"))
                        .unwrap_or_default()
                )
            })
            .collect::<Vec<_>>()
    };
    assert_eq!(codes(PATH_SCENE), Vec::<String>::new());
    let base = "render : { mode = path }\ncamera : { resolution = { width = 8 height = 8 } }\n";
    assert_eq!(codes(&format!("{base}primitives : {{ sphere = {{ material = glas }} }}\nmaterials : {{ material = {{ name = glass type = glass }} }}")), vec!["unknown_material@3>glass"]);
    assert_eq!(
        codes(&format!(
            "{base}primitives : {{ sphere = {{ type = rubber }} }}"
        )),
        vec!["invalid_value@3"]
    );
    assert_eq!(codes("render : { samles = 4 }\ncamera : { resolution = { width = 8 height = 8 } }\nprimitives : { plane = { } }"), vec!["unknown_key@1>samples", "no_light@0"]);
    assert_eq!(codes(&format!("{base}primitives : {{\n mesh = {{ vertices = {{ 0 0 0  1 0 0  0 1 0 }} faces = {{ 0 1 3 }} }}\n}}")), vec!["bad_mesh@4"]);
    assert_eq!(
        codes("render : { }\ncamera : {\n resolution = { width = 8 height = 8 }\n"),
        vec!["unbalanced_braces@2"]
    );
    assert_eq!(
        codes(&format!(
            "{base}primitives : {{ sphere = {{ }} }}\nlights : {{ }}\nfrmae = 1"
        )),
        vec!["unknown_key@5>frame"]
    );
    let dark = "render : { mode = path sky = 0 }\ncamera : { resolution = { width = 8 height = 8 } }\nprimitives : { plane = { } }";
    assert_eq!(codes(dark), vec!["dark_scene@0"]);
    let report = check_scene(PATH_SCENE);
    assert_eq!(
        (report.scene.engine, report.scene.samples, report.scene.mode),
        (2, 4, "path")
    );
    assert_eq!(
        (
            report.scene.spheres,
            report.scene.planes,
            report.scene.triangles,
            report.scene.lights
        ),
        (1, 1, 7, 2)
    );
}

#[test]
fn scenes_written_by_the_site_editor_are_valid() {
    // FrontEnd/utils/scene.ts `sceneToCfg`, "Photoréaliste" quality.
    let text = include_str!("fixtures/editor_photo_scene.cfg");
    let report = check_scene(text);
    assert!(report.issues.is_empty(), "{:#?}", report.issues);
    assert_eq!(
        (report.scene.engine, report.scene.samples, report.scene.mode),
        (2, 256, "path")
    );
    let tile = render_scene(
        &text.replace("samples = 256", "samples = 1"),
        RenderOptions {
            x_start: Some(600),
            x_end: Some(604),
            y_start: Some(400),
            y_end: Some(402),
            ..RenderOptions::default()
        },
    );
    assert_eq!(tile.len(), 4 * 2 * 3);
}
