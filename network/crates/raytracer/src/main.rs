//! `silicium-raytracer`: deterministic CPU raytracer used by every compute node.
//!
//! Renders a `.cfg` scene to a binary PPM, optionally only a rectangular tile.
//! Output must be byte-identical across machines so that another peer can verify it.
//! Usage: `silicium-raytracer <scene.cfg> --output <out.ppm> [--x-start ..] [--threads N]`.
//!
//! Pipeline steps (JSON on stdout, see `commands/`):
//! `split <scene.cfg>`, `milestones <tile.ppm>`, `verify <tile.ppm> --manifest ..`,
//! `reassemble --fragment .. --output ..`, `validate <tile.ppm>`, `png <tile.ppm>`,
//! `resolution <scene.cfg>`, `check <scene.cfg>`, `version`,
//! `import-obj <model.obj>`, `frames <scene.cfg> --output-dir <dir>`.
//!
//! The engine (`silicium_raytracer::engine`) handles anti-aliasing, a free
//! camera, materials, path tracing, meshes and animation (`--frame N`).
//!
//! The engine lives in the `silicium_raytracer` library (`src/lib.rs`); this
//! binary only parses arguments and writes files.

mod commands;

use silicium_raytracer::{engine, render::RenderOptions};
use std::{env, fs, io::Write, path::PathBuf, sync::Arc, time::Instant};

#[derive(Default)]
struct Arguments {
    scene: PathBuf,
    output: PathBuf,
    render: RenderOptions,
    /// Animation frame.
    frame: Option<f64>,
}

fn parse_arguments() -> Result<Arguments, String> {
    let values = env::args().skip(1).collect::<Vec<_>>();
    if values.is_empty() {
        return Err("usage: silicium-raytracer <scene.cfg> --output <render.ppm>".into());
    }
    let mut parsed = Arguments {
        scene: PathBuf::from(&values[0]),
        ..Arguments::default()
    };
    let mut index = 1;
    while index < values.len() {
        let key = values[index].as_str();
        let value = values
            .get(index + 1)
            .ok_or_else(|| format!("missing value for {key}"))?;
        match key {
            "--output" | "-o" => parsed.output = PathBuf::from(value),
            "--x-start" => parsed.render.x_start = value.parse().ok(),
            "--x-end" => parsed.render.x_end = value.parse().ok(),
            "--y-start" => parsed.render.y_start = value.parse().ok(),
            "--y-end" => parsed.render.y_end = value.parse().ok(),
            "--threads" => parsed.render.threads = value.parse().ok(),
            "--progress-file" => parsed.render.progress_file = Some(PathBuf::from(value)),
            "--frame" => {
                parsed.frame = Some(
                    value
                        .parse()
                        .map_err(|_| format!("invalid --frame: {value}"))?,
                )
            }
            _ => {}
        }
        index += 2;
    }
    if parsed.output.as_os_str().is_empty() {
        return Err("--output is required".into());
    }
    Ok(parsed)
}

fn run() -> Result<(), String> {
    let args = parse_arguments()?;
    let text = fs::read_to_string(&args.scene).map_err(|error| error.to_string())?;
    let started = Instant::now();
    let scene = Arc::new(engine::scene::build(&text, args.frame)?);
    let (pixels, width, height, threads) = engine::render(scene, &args.render);
    let engine = engine::ENGINE_VERSION;
    if let Some(parent) = args.output.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let mut output = fs::File::create(&args.output).map_err(|error| error.to_string())?;
    write!(output, "P6\n{width} {height}\n255\n").map_err(|error| error.to_string())?;
    output
        .write_all(&pixels)
        .map_err(|error| error.to_string())?;
    eprintln!(
        "{{\"renderer\":\"silicium-raytracer-rust\",\"engine\":{engine},\"threads\":{threads},\"width\":{width},\"height\":{height},\"duration_ms\":{}}}",
        started.elapsed().as_millis()
    );
    Ok(())
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if let Some(name) = args
        .first()
        .filter(|name| commands::NAMES.contains(&name.as_str()))
    {
        match commands::run(name, &args[1..]) {
            Ok((payload, code)) => {
                println!(
                    "{}",
                    serde_json::to_string_pretty(&payload).unwrap_or_default()
                );
                std::process::exit(code);
            }
            Err(error) => {
                eprintln!("silicium_raytracer_error:{error}");
                std::process::exit(1);
            }
        }
    }
    if let Err(error) = run() {
        eprintln!("silicium_raytracer_error:{error}");
        std::process::exit(2);
    }
}
