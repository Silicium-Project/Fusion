//! Import of Wavefront `.obj` models as a `mesh` block.
//!
//! The network sends one scene file per job, so a model is written into the
//! scene itself (`silicium-raytracer import-obj model.obj`) rather than
//! referenced by path.

/// A triangulated model.
#[derive(Debug, Default, PartialEq)]
pub struct Model {
    pub vertices: Vec<[f64; 3]>,
    pub faces: Vec<[usize; 3]>,
}

/// Reads the `v` and `f` lines of an OBJ file (polygons are split into
/// triangles; `f 1/2/3 ...` and negative indices are understood).
pub fn parse(text: &str) -> Result<Model, String> {
    let mut model = Model::default();
    for (number, line) in text.lines().enumerate() {
        let mut parts = line.split_whitespace();
        match parts.next() {
            Some("v") => {
                let values: Vec<f64> = parts
                    .take(3)
                    .map(|p| p.parse::<f64>())
                    .collect::<Result<_, _>>()
                    .map_err(|_| format!("line {}: bad vertex", number + 1))?;
                if values.len() != 3 {
                    return Err(format!("line {}: a vertex needs 3 coordinates", number + 1));
                }
                model.vertices.push([values[0], values[1], values[2]]);
            }
            Some("f") => {
                let count = model.vertices.len() as i64;
                let indices = parts
                    .map(|part| {
                        let raw: i64 = part
                            .split('/')
                            .next()
                            .unwrap_or("")
                            .parse()
                            .map_err(|_| format!("line {}: bad face", number + 1))?;
                        let index = if raw < 0 { count + raw } else { raw - 1 };
                        if index < 0 || index >= count {
                            return Err(format!(
                                "line {}: face uses a vertex that does not exist",
                                number + 1
                            ));
                        }
                        Ok(index as usize)
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                if indices.len() < 3 {
                    return Err(format!("line {}: a face needs 3 vertices", number + 1));
                }
                for i in 1..indices.len() - 1 {
                    model.faces.push([indices[0], indices[i], indices[i + 1]]);
                }
            }
            _ => {}
        }
    }
    if model.faces.is_empty() {
        return Err("the file has no faces".into());
    }
    Ok(model)
}

impl Model {
    /// Turns a y-up model (the OBJ habit) into the scene's z-up axes.
    pub fn y_up_to_z_up(&mut self) {
        for v in &mut self.vertices {
            *v = [v[0], -v[2], v[1]];
        }
    }

    /// Centres the model on the origin, sets it on z = 0 and scales it so its
    /// largest side is `size`.
    pub fn fit(&mut self, size: f64) {
        let mut low = [f64::INFINITY; 3];
        let mut high = [f64::NEG_INFINITY; 3];
        for v in &self.vertices {
            for axis in 0..3 {
                low[axis] = low[axis].min(v[axis]);
                high[axis] = high[axis].max(v[axis]);
            }
        }
        let largest = (0..3).map(|a| high[a] - low[a]).fold(0.0, f64::max);
        if largest <= 0.0 {
            return;
        }
        let factor = size / largest;
        let centre = [(low[0] + high[0]) / 2.0, (low[1] + high[1]) / 2.0, low[2]];
        for v in &mut self.vertices {
            for axis in 0..3 {
                v[axis] = (v[axis] - centre[axis]) * factor;
            }
        }
    }

    /// The `mesh = { ... }` block, to paste in `primitives`.
    pub fn to_block(&self, material: &str, source: &str) -> String {
        let number = |value: f64| {
            let text = format!("{:.5}", value);
            let text = text.trim_end_matches('0').trim_end_matches('.');
            if text == "-0" {
                "0".to_string()
            } else {
                text.to_string()
            }
        };
        let mut out = format!(
            "\t# {} — {} vertices, {} triangles\n\tmesh = {{\n\t\tmaterial = {}\n\t\tvertices = {{\n",
            source.replace('\n', " "),
            self.vertices.len(),
            self.faces.len(),
            material
        );
        for v in &self.vertices {
            out.push_str(&format!(
                "\t\t\t{} {} {}\n",
                number(v[0]),
                number(v[1]),
                number(v[2])
            ));
        }
        out.push_str("\t\t}\n\t\tfaces = {\n");
        for f in &self.faces {
            out.push_str(&format!("\t\t\t{} {} {}\n", f[0], f[1], f[2]));
        }
        out.push_str("\t\t}\n\t}\n");
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_quads_negative_indices_and_slashes() {
        let model = parse("# cube face\nv 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1/1/1 2/2/2 3/3/3 4/4/4\nf -4 -3 -2\n").unwrap();
        assert_eq!(model.vertices.len(), 4);
        assert_eq!(model.faces, vec![[0, 1, 2], [0, 2, 3], [0, 1, 2]]);
        assert!(parse("v 0 0 0\nf 1 2 3\n").is_err());
    }

    #[test]
    fn fits_the_model_on_the_floor() {
        let mut model = parse("v 0 0 0\nv 4 0 0\nv 0 2 1\nf 1 2 3\n").unwrap();
        model.fit(2.0);
        assert_eq!(model.vertices[1], [1.0, -0.5, 0.0]);
        assert!(model.to_block("gold", "test.obj").contains("mesh = {"));
    }
}
