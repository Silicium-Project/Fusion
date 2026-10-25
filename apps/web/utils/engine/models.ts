// Triangle models for `mesh` objects: Wavefront `.obj` import (port of the
// raytracer's `engine/obj.rs`) and a few built-in shapes. Models are z-up,
// centred on the origin, resting on z = 0 (as `fit` leaves them).

export interface Model {
  vertices: number[];
  faces: number[];
}

/** Reads the `v` and `f` lines of an OBJ file (polygons split into triangles); throws an `Error`. */
export function parseObj(text: string): Model {
  const vertices: number[] = [];
  const faces: number[] = [];
  text.split(/\r?\n/).forEach((line, index) => {
    const parts = line.trim().split(/\s+/);
    if (parts[0] === 'v') {
      const values = parts.slice(1, 4).map(Number);
      if (values.length !== 3 || values.some((value) => !Number.isFinite(value)))
        throw new Error(`line ${index + 1}: bad vertex`);
      vertices.push(...values);
    } else if (parts[0] === 'f') {
      const count = vertices.length / 3;
      const indices = parts.slice(1).map((part) => {
        const raw = Number.parseInt(part.split('/')[0] ?? '', 10);
        if (!Number.isFinite(raw)) throw new Error(`line ${index + 1}: bad face`);
        const at = raw < 0 ? count + raw : raw - 1;
        if (at < 0 || at >= count)
          throw new Error(`line ${index + 1}: face uses a vertex that does not exist`);
        return at;
      });
      if (indices.length < 3) throw new Error(`line ${index + 1}: a face needs 3 vertices`);
      for (let i = 1; i < indices.length - 1; i += 1)
        faces.push(indices[0]!, indices[i]!, indices[i + 1]!);
    }
  });
  if (!faces.length) throw new Error('the file has no faces');
  return { vertices, faces };
}

/** Turns a y-up model (the OBJ habit) into z-up axes. */
export function yUpToZUp(model: Model): Model {
  const vertices = [...model.vertices];
  for (let i = 0; i < vertices.length; i += 3) {
    const y = vertices[i + 1]!;
    vertices[i + 1] = -vertices[i + 2]!;
    vertices[i + 2] = y;
  }
  return { vertices, faces: model.faces };
}

/** Centres the model, sets it on z = 0 and scales it so its largest side is `size`. */
export function fit(model: Model, size = 1): Model {
  const low = [Infinity, Infinity, Infinity];
  const high = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < model.vertices.length; i += 1) {
    low[i % 3] = Math.min(low[i % 3]!, model.vertices[i]!);
    high[i % 3] = Math.max(high[i % 3]!, model.vertices[i]!);
  }
  const largest = Math.max(0, ...[0, 1, 2].map((axis) => high[axis]! - low[axis]!));
  if (largest <= 0) return model;
  const factor = size / largest;
  const centre = [(low[0]! + high[0]!) / 2, (low[1]! + high[1]!) / 2, low[2]!];
  return {
    vertices: model.vertices.map((value, i) =>
      Number(((value - centre[i % 3]!) * factor).toFixed(5)),
    ),
    faces: model.faces,
  };
}

export const BUILTIN_MODELS = ['pyramid', 'gem', 'cylinder', 'torus'] as const;
export type BuiltinModel = (typeof BUILTIN_MODELS)[number];

function revolve(profile: [number, number][], segments: number, closed: boolean): Model {
  // Rings of points around the z axis; `closed` joins the last ring to the first (torus).
  const vertices: number[] = [];
  const faces: number[] = [];
  const rings = profile.length;
  for (let s = 0; s < segments; s += 1) {
    const angle = (2 * Math.PI * s) / segments;
    for (const [radius, z] of profile)
      vertices.push(radius * Math.cos(angle), radius * Math.sin(angle), z);
  }
  const at = (s: number, r: number) => (s % segments) * rings + (r % rings);
  for (let s = 0; s < segments; s += 1) {
    for (let r = 0; r < (closed ? rings : rings - 1); r += 1) {
      faces.push(
        at(s, r),
        at(s + 1, r),
        at(s + 1, r + 1),
        at(s, r),
        at(s + 1, r + 1),
        at(s, r + 1),
      );
    }
  }
  return { vertices, faces };
}

/** A built-in model, 1 unit large. */
export function builtinModel(name: BuiltinModel): Model {
  switch (name) {
    case 'pyramid':
      return fit({
        vertices: [-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0, 0, 0, 1.4],
        faces: [0, 2, 1, 0, 3, 2, 0, 1, 4, 1, 2, 4, 2, 3, 4, 3, 0, 4],
      });
    case 'gem': {
      // Icosahedron.
      const p = (1 + Math.sqrt(5)) / 2;
      const vertices = [
        -1,
        p,
        0,
        1,
        p,
        0,
        -1,
        -p,
        0,
        1,
        -p,
        0,
        0,
        -1,
        p,
        0,
        1,
        p,
        0,
        -1,
        -p,
        0,
        1,
        -p,
        p,
        0,
        -1,
        p,
        0,
        1,
        -p,
        0,
        -1,
        -p,
        0,
        1,
      ];
      const faces = [
        0, 11, 5, 0, 5, 1, 0, 1, 7, 0, 7, 10, 0, 10, 11, 1, 5, 9, 5, 11, 4, 11, 10, 2, 10, 7, 6, 7,
        1, 8, 3, 9, 4, 3, 4, 2, 3, 2, 6, 3, 6, 8, 3, 8, 9, 4, 9, 5, 2, 4, 11, 6, 2, 10, 8, 6, 7, 9,
        8, 1,
      ];
      return fit({ vertices, faces });
    }
    case 'cylinder': {
      const side = revolve(
        [
          [0, 0],
          [1, 0],
          [1, 2],
          [0, 2],
        ],
        32,
        false,
      );
      return fit(side);
    }
    case 'torus': {
      const tube: [number, number][] = [];
      for (let i = 0; i < 12; i += 1) {
        const angle = (2 * Math.PI * i) / 12;
        tube.push([1 + 0.38 * Math.cos(angle), 0.38 * Math.sin(angle)]);
      }
      return fit(revolve(tube, 32, true));
    }
  }
}
