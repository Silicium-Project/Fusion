//! Binary PPM (P6, 8-bit) reading and writing, with the error codes of the
//! Python pipeline.

/// A decoded P6 image.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Ppm {
    pub width: usize,
    pub height: usize,
    pub pixels: Vec<u8>,
}

/// Python `chr(byte).isspace()` for a single byte (Latin-1).
fn is_space(byte: u8) -> bool {
    matches!(byte, 9..=13 | 28..=32 | 0x85 | 0xa0)
}

/// Python `int(token)` for the header numbers (sign, digits, `_` separators).
fn parse_int(token: &[u8], source: &str) -> Result<i64, String> {
    let text = std::str::from_utf8(token).map_err(|_| format!("invalid_ppm_header:{source}"))?;
    let (sign, digits) = match text.as_bytes().first() {
        Some(b'-') => (-1, &text[1..]),
        Some(b'+') => (1, &text[1..]),
        _ => (1, text),
    };
    let valid = !digits.is_empty()
        && !digits.starts_with('_')
        && !digits.ends_with('_')
        && !digits.contains("__")
        && digits
            .bytes()
            .all(|byte| byte.is_ascii_digit() || byte == b'_');
    if !valid {
        return Err(format!("invalid_ppm_header:{source}"));
    }
    digits
        .replace('_', "")
        .parse::<i64>()
        .map(|value| sign * value)
        .map_err(|_| format!("invalid_ppm_header:{source}"))
}

/// Parses a P6 image; `source` only labels the error messages.
pub fn parse(data: &[u8], source: &str) -> Result<Ppm, String> {
    let mut idx = 0usize;
    let token = |idx: &mut usize| -> &[u8] {
        loop {
            while *idx < data.len() && is_space(data[*idx]) {
                *idx += 1;
            }
            if *idx < data.len() && data[*idx] == b'#' {
                while *idx < data.len() && data[*idx] != b'\r' && data[*idx] != b'\n' {
                    *idx += 1;
                }
                continue;
            }
            let start = *idx;
            while *idx < data.len() && !is_space(data[*idx]) {
                *idx += 1;
            }
            return &data[start..*idx];
        }
    };
    if token(&mut idx) != b"P6" {
        return Err(format!("unsupported_ppm_magic:{source}"));
    }
    let width = parse_int(token(&mut idx), source)?;
    let height = parse_int(token(&mut idx), source)?;
    let max_value = parse_int(token(&mut idx), source)?;
    if max_value != 255 {
        return Err(format!("unsupported_ppm_max_value:{max_value}"));
    }
    if idx >= data.len() || !matches!(data[idx], b' ' | b'\t' | b'\r' | b'\n') {
        return Err(format!("missing_ppm_raster_separator:{source}"));
    }
    if data[idx..].starts_with(b"\r\n") {
        idx += 2;
    } else {
        idx += 1;
    }
    let pixels = &data[idx..];
    let expected = width * height * 3;
    if width < 0 || height < 0 || pixels.len() as i64 != expected {
        return Err(format!(
            "invalid_ppm_payload_size:{source}:expected={expected}:actual={}",
            pixels.len()
        ));
    }
    Ok(Ppm {
        width: width as usize,
        height: height as usize,
        pixels: pixels.to_vec(),
    })
}

/// Encodes a P6 image exactly like the Python pipeline.
pub fn encode(width: usize, height: usize, pixels: &[u8]) -> Vec<u8> {
    let mut out = format!("P6\n{width} {height}\n255\n").into_bytes();
    out.extend_from_slice(pixels);
    out
}

/// SHA-256 of the raster only (header excluded), as used by the milestones.
pub fn pixel_sha256(data: &[u8]) -> Result<String, String> {
    Ok(super::sha256_hex(&parse(data, "<bytes>")?.pixels))
}

/// Checks a rendered tile before it is accepted (format, size, hash).
/// Returns `(width, height, sha256_of_whole_file)`.
pub fn validate_fragment(
    data: &[u8],
    task_id: &str,
    expected_width: Option<usize>,
    expected_height: Option<usize>,
    expected_hash: Option<&str>,
) -> Result<(usize, usize, String), String> {
    let image = parse(data, task_id)
        .map_err(|error| format!("raytracer_fragment_invalid_ppm:task={task_id}:{error}"))?;
    if let (Some(width), Some(height)) = (expected_width, expected_height) {
        if (width, height) != (image.width, image.height) {
            return Err(format!(
                "raytracer_fragment_dimensions_mismatch:task={task_id}:expected={width}x{height}:actual={}x{}",
                image.width, image.height
            ));
        }
    } else if let Some(width) = expected_width.filter(|width| *width != image.width) {
        return Err(format!(
            "raytracer_fragment_width_mismatch:task={task_id}:expected={width}:actual={}",
            image.width
        ));
    } else if let Some(height) = expected_height.filter(|height| *height != image.height) {
        return Err(format!(
            "raytracer_fragment_height_mismatch:task={task_id}:expected={height}:actual={}",
            image.height
        ));
    }
    let actual = super::sha256_hex(data);
    if let Some(expected) = expected_hash {
        let normalized = expected
            .strip_prefix("sha256:")
            .unwrap_or(expected)
            .to_lowercase();
        if actual != normalized {
            return Err(format!(
                "raytracer_fragment_hash_mismatch:task={task_id}:expected={normalized}:actual={actual}"
            ));
        }
    }
    Ok((image.width, image.height, actual))
}
