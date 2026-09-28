use std::{
    env, fs,
    io::Write,
    ops::{Add, Div, Mul, Neg, Sub},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicUsize, Ordering},
        mpsc, Arc,
    },
    thread,
    time::Instant,
};

const EPSILON: f64 = 1e-4;
const MAX_DEPTH: u32 = 3;

#[derive(Clone, Copy, Debug, Default)]
struct Vec3 {
    x: f64,
    y: f64,
    z: f64,
}

impl Vec3 {
    fn new(x: f64, y: f64, z: f64) -> Self {
        Self { x, y, z }
    }
    fn dot(self, other: Self) -> f64 {
        self.x * other.x + self.y * other.y + self.z * other.z
    }
    fn length(self) -> f64 {
        self.dot(self).sqrt()
    }
    fn normalized(self) -> Self {
        let length = self.length();
        if length <= EPSILON {
            Self::default()
        } else {
            self / length
        }
    }
    fn hadamard(self, other: Self) -> Self {
        Self::new(self.x * other.x, self.y * other.y, self.z * other.z)
    }
    fn reflect(self, normal: Self) -> Self {
        self - normal * (2.0 * self.dot(normal))
    }
    fn clamp(self) -> Self {
        Self::new(
            self.x.clamp(0.0, 1.0),
            self.y.clamp(0.0, 1.0),
            self.z.clamp(0.0, 1.0),
        )
    }
}

impl Add for Vec3 {
    type Output = Self;
    fn add(self, rhs: Self) -> Self {
        Self::new(self.x + rhs.x, self.y + rhs.y, self.z + rhs.z)
    }
}
impl Sub for Vec3 {
    type Output = Self;
    fn sub(self, rhs: Self) -> Self {
        Self::new(self.x - rhs.x, self.y - rhs.y, self.z - rhs.z)
    }
}
impl Mul<f64> for Vec3 {
    type Output = Self;
    fn mul(self, rhs: f64) -> Self {
        Self::new(self.x * rhs, self.y * rhs, self.z * rhs)
    }
}
impl Div<f64> for Vec3 {
    type Output = Self;
    fn div(self, rhs: f64) -> Self {
        self * (1.0 / rhs)
    }
}
impl Neg for Vec3 {
    type Output = Self;
    fn neg(self) -> Self {
        self * -1.0
    }
}

#[derive(Clone, Copy)]
struct Ray {
    origin: Vec3,
    direction: Vec3,
}

#[derive(Clone, Copy)]
struct Material {
    color: Vec3,
    reflectivity: f64,
    specular: f64,
    shininess: f64,
}

#[derive(Clone)]
enum Primitive {
    Sphere {
        center: Vec3,
        radius: f64,
        material: Material,
    },
    Plane {
        point: Vec3,
        normal: Vec3,
        material: Material,
    },
}

#[derive(Clone, Copy)]
struct Light {
    position: Vec3,
    intensity: f64,
    color: Vec3,
}

#[derive(Clone)]
struct Scene {
    width: usize,
    height: usize,
    fov: f64,
    camera: Vec3,
    primitives: Vec<Primitive>,
    lights: Vec<Light>,
}

#[derive(Clone, Copy)]
struct Hit {
    distance: f64,
    point: Vec3,
    normal: Vec3,
    material: Material,
}

impl Primitive {
    fn intersect(&self, ray: Ray) -> Option<Hit> {
        match self {
            Primitive::Sphere {
                center,
                radius,
                material,
            } => {
                let offset = ray.origin - *center;
                let half_b = offset.dot(ray.direction);
                let c = offset.dot(offset) - radius * radius;
                let discriminant = half_b * half_b - c;
                if discriminant < 0.0 {
                    return None;
                }
                let root = discriminant.sqrt();
                let first = -half_b - root;
                let second = -half_b + root;
                let distance = if first > EPSILON {
                    first
                } else if second > EPSILON {
                    second
                } else {
                    return None;
                };
                let point = ray.origin + ray.direction * distance;
                Some(Hit {
                    distance,
                    point,
                    normal: (point - *center).normalized(),
                    material: *material,
                })
            }
            Primitive::Plane {
                point,
                normal,
                material,
            } => {
                let denominator = normal.dot(ray.direction);
                if denominator.abs() < EPSILON {
                    return None;
                }
                let distance = (*point - ray.origin).dot(*normal) / denominator;
                if distance <= EPSILON {
                    return None;
                }
                Some(Hit {
                    distance,
                    point: ray.origin + ray.direction * distance,
                    normal: if denominator < 0.0 { *normal } else { -*normal },
                    material: *material,
                })
            }
        }
    }
}

fn tokens(text: &str) -> Vec<String> {
    let mut result = Vec::new();
    let mut current = String::new();
    let flush = |current: &mut String, result: &mut Vec<String>| {
        if !current.is_empty() {
            result.push(std::mem::take(current));
        }
    };
    for character in text.chars() {
        if character.is_ascii_alphanumeric()
            || character == '_'
            || character == '.'
            || ((character == '-' || character == '+') && current.is_empty())
        {
            current.push(character);
        } else {
            flush(&mut current, &mut result);
            if "{}=:;".contains(character) {
                result.push(character.to_string());
            }
        }
    }
    flush(&mut current, &mut result);
    result
}

fn blocks(source: &[String], name: &str) -> Vec<Vec<String>> {
    let mut result = Vec::new();
    let mut index = 0;
    while index + 2 < source.len() {
        if source[index] != name
            || !matches!(source[index + 1].as_str(), "=" | ":")
            || source[index + 2] != "{"
        {
            index += 1;
            continue;
        }
        let mut depth = 1_i32;
        let mut cursor = index + 3;
        while cursor < source.len() && depth > 0 {
            match source[cursor].as_str() {
                "{" => depth += 1,
                "}" => depth -= 1,
                _ => {}
            }
            cursor += 1;
        }
        if depth == 0 {
            result.push(source[index + 3..cursor - 1].to_vec());
            index = cursor;
        } else {
            break;
        }
    }
    result
}

fn scalar(source: &[String], key: &str, default: f64) -> f64 {
    source
        .windows(3)
        .find(|items| items[0] == key && items[1] == "=")
        .and_then(|items| items[2].parse::<f64>().ok())
        .unwrap_or(default)
}

fn material(source: &[String], default_reflectivity: f64) -> Material {
    Material {
        color: Vec3::new(
            scalar(source, "r", 200.0) / 255.0,
            scalar(source, "g", 200.0) / 255.0,
            scalar(source, "b", 200.0) / 255.0,
        ),
        reflectivity: scalar(
            source,
            "reflectivity",
            scalar(source, "reflection", default_reflectivity),
        )
        .clamp(0.0, 0.95),
        specular: scalar(source, "specular", 0.65).clamp(0.0, 2.0),
        shininess: scalar(source, "shininess", 72.0).clamp(1.0, 512.0),
    }
}

fn parse_scene(path: &Path) -> Result<Scene, String> {
    let text = fs::read_to_string(path).map_err(|error| error.to_string())?;
    let source = tokens(&text);
    let camera_block = blocks(&source, "camera")
        .into_iter()
        .next()
        .unwrap_or_default();
    let mut primitives = Vec::new();
    for sphere in blocks(&source, "sphere") {
        primitives.push(Primitive::Sphere {
            center: Vec3::new(
                scalar(&sphere, "x", 0.0),
                scalar(&sphere, "y", 0.0),
                scalar(&sphere, "z", 0.0),
            ),
            radius: scalar(&sphere, "radius", 1.0).max(EPSILON),
            material: material(&sphere, 0.32),
        });
    }
    for plane in blocks(&source, "plane") {
        primitives.push(Primitive::Plane {
            point: Vec3::new(
                scalar(&plane, "x", 0.0),
                scalar(&plane, "y", 0.0),
                scalar(&plane, "z", 0.0),
            ),
            normal: Vec3::new(
                scalar(&plane, "normal_x", 0.0),
                scalar(&plane, "normal_y", 0.0),
                scalar(&plane, "normal_z", 1.0),
            )
            .normalized(),
            material: material(&plane, 0.12),
        });
    }
    let mut lights = Vec::new();
    for point in blocks(&source, "point") {
        lights.push(Light {
            position: Vec3::new(
                scalar(&point, "x", 4.0),
                scalar(&point, "y", 0.0),
                scalar(&point, "z", 5.0),
            ),
            intensity: scalar(&point, "intensity", 450.0).max(0.0),
            color: Vec3::new(
                scalar(&point, "r", 255.0) / 255.0,
                scalar(&point, "g", 255.0) / 255.0,
                scalar(&point, "b", 255.0) / 255.0,
            ),
        });
    }
    if lights.is_empty() {
        lights.push(Light {
            position: Vec3::new(4.0, 0.0, 5.0),
            intensity: 450.0,
            color: Vec3::new(1.0, 1.0, 1.0),
        });
    }
    Ok(Scene {
        width: scalar(&camera_block, "width", 320.0).max(1.0) as usize,
        height: scalar(&camera_block, "height", 200.0).max(1.0) as usize,
        fov: scalar(&camera_block, "fieldOfView", 55.0).clamp(1.0, 179.0),
        camera: Vec3::new(
            scalar(&camera_block, "x", 0.0),
            scalar(&camera_block, "y", 0.0),
            scalar(&camera_block, "z", 0.0),
        ),
        primitives,
        lights,
    })
}

fn nearest_hit(scene: &Scene, ray: Ray) -> Option<Hit> {
    scene
        .primitives
        .iter()
        .filter_map(|primitive| primitive.intersect(ray))
        .min_by(|left, right| left.distance.total_cmp(&right.distance))
}

fn background(direction: Vec3) -> Vec3 {
    let amount = (direction.z + 1.0) * 0.5;
    Vec3::new(0.04, 0.07, 0.13) * (1.0 - amount) + Vec3::new(0.34, 0.55, 0.9) * amount
}

fn trace(scene: &Scene, ray: Ray, depth: u32) -> Vec3 {
    let Some(hit) = nearest_hit(scene, ray) else {
        return background(ray.direction);
    };
    let mut diffuse_light = Vec3::new(0.09, 0.09, 0.11);
    let mut specular_light = Vec3::default();
    let view = -ray.direction;
    for light in &scene.lights {
        let displacement = light.position - hit.point;
        let distance_squared = displacement.dot(displacement).max(1.0);
        let distance = distance_squared.sqrt();
        let light_direction = displacement / distance;
        let shadow_ray = Ray {
            origin: hit.point + hit.normal * (EPSILON * 4.0),
            direction: light_direction,
        };
        if nearest_hit(scene, shadow_ray)
            .map(|shadow| shadow.distance < distance - EPSILON)
            .unwrap_or(false)
        {
            continue;
        }
        let attenuation = (light.intensity / distance_squared).min(1.5);
        let lambert = hit.normal.dot(light_direction).max(0.0);
        diffuse_light = diffuse_light + light.color * (lambert * attenuation);
        let reflected_light = (-light_direction).reflect(hit.normal).normalized();
        let highlight = reflected_light
            .dot(view)
            .max(0.0)
            .powf(hit.material.shininess)
            * hit.material.specular
            * attenuation;
        specular_light = specular_light + light.color * highlight;
    }
    let local = hit.material.color.hadamard(diffuse_light) + specular_light;
    if depth >= MAX_DEPTH || hit.material.reflectivity <= 0.0 {
        return local.clamp();
    }
    let reflected = trace(
        scene,
        Ray {
            origin: hit.point + hit.normal * (EPSILON * 4.0),
            direction: ray.direction.reflect(hit.normal).normalized(),
        },
        depth + 1,
    );
    (local * (1.0 - hit.material.reflectivity) + reflected * hit.material.reflectivity).clamp()
}

#[derive(Default)]
struct Arguments {
    scene: PathBuf,
    output: PathBuf,
    x_start: Option<usize>,
    x_end: Option<usize>,
    y_start: Option<usize>,
    y_end: Option<usize>,
    threads: Option<usize>,
    progress_file: Option<PathBuf>,
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
            "--x-start" => parsed.x_start = value.parse().ok(),
            "--x-end" => parsed.x_end = value.parse().ok(),
            "--y-start" => parsed.y_start = value.parse().ok(),
            "--y-end" => parsed.y_end = value.parse().ok(),
            "--threads" => parsed.threads = value.parse().ok(),
            "--progress-file" => parsed.progress_file = Some(PathBuf::from(value)),
            _ => {}
        }
        index += 2;
    }
    if parsed.output.as_os_str().is_empty() {
        return Err("--output is required".into());
    }
    Ok(parsed)
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

fn render(scene: Arc<Scene>, args: &Arguments) -> (Vec<u8>, usize, usize, usize) {
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

fn run() -> Result<(), String> {
    let args = parse_arguments()?;
    let scene = Arc::new(parse_scene(&args.scene)?);
    let started = Instant::now();
    let (pixels, width, height, threads) = render(scene, &args);
    if let Some(parent) = args.output.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let mut output = fs::File::create(&args.output).map_err(|error| error.to_string())?;
    write!(output, "P6\n{width} {height}\n255\n").map_err(|error| error.to_string())?;
    output
        .write_all(&pixels)
        .map_err(|error| error.to_string())?;
    eprintln!(
        "{{\"renderer\":\"silicium-raytracer-rust\",\"threads\":{threads},\"width\":{width},\"height\":{height},\"duration_ms\":{}}}",
        started.elapsed().as_millis()
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("silicium_raytracer_error:{error}");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parser_keeps_shiny_material_and_scene_dimensions() {
        let path = env::temp_dir().join("silicium-native-raytracer-test.cfg");
        fs::write(
            &path,
            "camera : { resolution = { width = 64 height = 32 } fieldOfView = 60 }\n\
             primitives : { sphere = { x = 5 y = 0 z = 0 radius = 1 reflection = 0.7 shininess = 120 color = { r = 255 g = 0 b = 0 } } }\n\
             lights : { point = { x = 2 y = -2 z = 4 intensity = 400 } }",
        )
        .unwrap();
        let scene = parse_scene(&path).unwrap();
        fs::remove_file(path).unwrap();
        assert_eq!((scene.width, scene.height), (64, 32));
        match &scene.primitives[0] {
            Primitive::Sphere { material, .. } => {
                assert_eq!(material.reflectivity, 0.7);
                assert_eq!(material.shininess, 120.0);
            }
            _ => panic!("expected sphere"),
        }
    }

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
        let args = Arguments {
            x_start: Some(4),
            x_end: Some(20),
            y_start: Some(3),
            y_end: Some(15),
            threads: Some(4),
            ..Arguments::default()
        };
        let (pixels, width, height, threads) = render(scene, &args);
        assert_eq!((width, height, threads), (16, 12, 4));
        assert_eq!(pixels.len(), width * height * 3);
    }
}
