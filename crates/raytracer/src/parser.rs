//! `.cfg` scene parser: a tolerant tokenizer that reads `camera`, `sphere`,
//! `plane` and `point` blocks and falls back to defaults for missing keys.

use crate::{
    math::Vec3,
    scene::{Light, Material, Primitive, Scene},
    EPSILON,
};
use std::{fs, path::Path};

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

/// Reads and parses a scene file.
pub fn parse_scene(path: &Path) -> Result<Scene, String> {
    let text = fs::read_to_string(path).map_err(|error| error.to_string())?;
    Ok(parse_scene_text(&text))
}

/// Parses the text of a scene file (never fails: missing keys take defaults).
pub fn parse_scene_text(text: &str) -> Scene {
    let source = tokens(text);
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
    Scene {
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
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;

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
}
