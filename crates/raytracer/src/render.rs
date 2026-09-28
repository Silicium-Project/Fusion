//! Multi-threaded tile rendering with optional progress reporting.

use crate::{
    math::{Ray, Vec3},
    scene::Scene,
    trace::trace,
};
use std::{
    env, fs,
    path::PathBuf,
    sync::{
        atomic::{AtomicUsize, Ordering},
        mpsc, Arc,
    },
    thread,
    time::Instant,
};

/// Which part of the image to render and how.
#[derive(Default)]
pub struct RenderOptions {
    pub x_start: Option<usize>,
    pub x_end: Option<usize>,
    pub y_start: Option<usize>,
    pub y_end: Option<usize>,
    /// Worker threads; defaults to `SILICIUM_RAYTRACER_THREADS`, then to the CPU count.
    pub threads: Option<usize>,
    /// Where to write `silicium.task-progress.v1` JSON while rendering.
    pub progress_file: Option<PathBuf>,
}

fn write_progress(
    path: Option<&PathBuf>,
    completed_rows: usize,
    total_rows: usize,
    width: usize,
    threads: usize,
    started: Instant,
) {
    let Some(path) = path else {
        return;
    };
    let elapsed = started.elapsed().as_secs_f64();
    let total_pixels = width.saturating_mul(total_rows);
    let completed_pixels = width.saturating_mul(completed_rows);
    let rate = if elapsed > 0.0 {
        completed_pixels as f64 / elapsed
    } else {
        0.0
    };
    let remaining = total_pixels.saturating_sub(completed_pixels);
    let eta = if rate > 0.0 {
        remaining as f64 / rate
    } else {
        0.0
    };
    let progress = if total_rows > 0 {
        100.0 * completed_rows as f64 / total_rows as f64
    } else {
        100.0
    };
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let _ = fs::write(
        path,
        format!(
            "{{\"schema\":\"silicium.task-progress.v1\",\"phase\":\"rendering\",\"progress_percent\":{progress:.3},\"completed_units\":{completed_rows},\"total_units\":{total_rows},\"unit\":\"rows\",\"pixels_completed\":{completed_pixels},\"pixels_total\":{total_pixels},\"throughput_units_per_second\":{rate:.3},\"eta_seconds\":{eta:.3},\"elapsed_ms\":{},\"threads\":{threads}}}",
            started.elapsed().as_millis()
        ),
    );
}

/// Renders the requested tile on a pool of threads.
///
/// Returns `(rgb_bytes, width, height, threads_used)`.
pub fn render(scene: Arc<Scene>, args: &RenderOptions) -> (Vec<u8>, usize, usize, usize) {
    let x_start = args.x_start.unwrap_or(0).min(scene.width);
    let x_end = args
        .x_end
        .unwrap_or(scene.width)
        .clamp(x_start, scene.width);
    let y_start = args.y_start.unwrap_or(0).min(scene.height);
    let y_end = args
        .y_end
        .unwrap_or(scene.height)
        .clamp(y_start, scene.height);
    let width = x_end - x_start;
    let height = y_end - y_start;
    let available = thread::available_parallelism()
        .map(|value| value.get())
        .unwrap_or(1);
    let environment_threads = env::var("SILICIUM_RAYTRACER_THREADS")
        .ok()
        .and_then(|value| value.parse::<usize>().ok());
    let thread_count = args
        .threads
        .or(environment_threads)
        .unwrap_or(available)
        .max(1)
        .min(height.max(1));
    let next_row = Arc::new(AtomicUsize::new(0));
    let (sender, receiver) = mpsc::channel();
    let started = Instant::now();
    let aspect = scene.width as f64 / scene.height as f64;
    let scale = (scene.fov.to_radians() * 0.5).tan();
    for _ in 0..thread_count {
        let scene = Arc::clone(&scene);
        let next_row = Arc::clone(&next_row);
        let sender = sender.clone();
        thread::spawn(move || loop {
            let local_y = next_row.fetch_add(1, Ordering::Relaxed);
            if local_y >= height {
                break;
            }
            let y = y_start + local_y;
            let mut row = Vec::with_capacity(width * 3);
            for x in x_start..x_end {
                let px = (2.0 * (x as f64 + 0.5) / scene.width as f64 - 1.0) * aspect * scale;
                let py = (1.0 - 2.0 * (y as f64 + 0.5) / scene.height as f64) * scale;
                let color = trace(
                    &scene,
                    Ray {
                        origin: scene.camera,
                        direction: Vec3::new(1.0, -px, py).normalized(),
                    },
                    0,
                )
                .clamp();
                for channel in [color.x, color.y, color.z] {
                    row.push((channel.sqrt() * 255.0).round().clamp(0.0, 255.0) as u8);
                }
            }
            if sender.send((local_y, row)).is_err() {
                break;
            }
        });
    }
    drop(sender);
    let mut pixels = vec![0_u8; width * height * 3];
    write_progress(
        args.progress_file.as_ref(),
        0,
        height,
        width,
        thread_count,
        started,
    );
    let progress_step = (height / 100).max(1);
    for completed in 1..=height {
        let (row, data) = receiver.recv().expect("renderer worker stopped");
        pixels[row * width * 3..(row + 1) * width * 3].copy_from_slice(&data);
        if completed == height || completed % progress_step == 0 {
            write_progress(
                args.progress_file.as_ref(),
                completed,
                height,
                width,
                thread_count,
                started,
            );
        }
    }
    (pixels, width, height, thread_count)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tile_render_is_parallel_and_has_exact_size() {
        let scene = Arc::new(Scene {
            width: 32,
            height: 24,
            fov: 55.0,
            camera: Vec3::default(),
            primitives: Vec::new(),
            lights: Vec::new(),
        });
        let args = RenderOptions {
            x_start: Some(4),
            x_end: Some(20),
            y_start: Some(3),
            y_end: Some(15),
            threads: Some(4),
            ..RenderOptions::default()
        };
        let (pixels, width, height, threads) = render(scene, &args);
        assert_eq!((width, height, threads), (16, 12, 4));
        assert_eq!(pixels.len(), width * height * 3);
    }
}
