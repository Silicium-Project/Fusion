// Vectors and randomness of the preview engine (port of the raytracer's
// `math.rs` and `engine/random.rs`). The random numbers are not the same as
// the network's (JavaScript has no cheap 64-bit integers): the preview's
// noise differs, the image converges to the same picture.

export class Vec3 {
  constructor(public x = 0, public y = 0, public z = 0) {}
  add(o: Vec3) { return new Vec3(this.x + o.x, this.y + o.y, this.z + o.z); }
  sub(o: Vec3) { return new Vec3(this.x - o.x, this.y - o.y, this.z - o.z); }
  mul(s: number) { return new Vec3(this.x * s, this.y * s, this.z * s); }
  div(s: number) { return this.mul(1 / s); }
  neg() { return new Vec3(-this.x, -this.y, -this.z); }
  dot(o: Vec3) { return this.x * o.x + this.y * o.y + this.z * o.z; }
  cross(o: Vec3) { return new Vec3(this.y * o.z - this.z * o.y, this.z * o.x - this.x * o.z, this.x * o.y - this.y * o.x); }
  hadamard(o: Vec3) { return new Vec3(this.x * o.x, this.y * o.y, this.z * o.z); }
  length() { return Math.sqrt(this.dot(this)); }
  normalized() {
    const length = this.length();
    return length <= EPSILON ? new Vec3() : this.div(length);
  }
  reflect(normal: Vec3) { return this.sub(normal.mul(2 * this.dot(normal))); }
  clamp() { return new Vec3(clamp01(this.x), clamp01(this.y), clamp01(this.z)); }
  maxComponent() { return Math.max(this.x, this.y, this.z); }
  axis(index: number) { return index === 0 ? this.x : index === 1 ? this.y : this.z; }
}

/** Distance under which two values are treated as equal (self-intersection guard). */
export const EPSILON = 1e-4;
const clamp01 = (value: number) => Math.min(1, Math.max(0, value));
const TAU = Math.PI * 2;

function hash32(value: number): number {
  let h = value | 0;
  h ^= h >>> 16; h = Math.imul(h, 0x7feb352d);
  h ^= h >>> 15; h = Math.imul(h, 0x846ca68b);
  h ^= h >>> 16;
  return h >>> 0;
}

/** Numbers of one sample of one pixel: they depend only on the pixel, the sample, the frame and the seed. */
export class Rng {
  private constructor(private state: number) {}

  static forSample(x: number, y: number, sample: number, frame: number, seed: number): Rng {
    let h = hash32(seed ^ 0x51c1d1);
    for (const part of [x, y, sample, frame]) h = hash32(h ^ ((part + 0x9e3779b9) | 0));
    return new Rng(h);
  }

  /** Next number in [0, 1) (mulberry32). */
  uniform(): number {
    let t = (this.state = (this.state + 0x6d2b79f5) | 0);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  inDisk(): [number, number] {
    const radius = Math.sqrt(this.uniform());
    const angle = TAU * this.uniform();
    return [radius * Math.cos(angle), radius * Math.sin(angle)];
  }

  onSphere(): Vec3 {
    const z = 1 - 2 * this.uniform();
    const r = Math.sqrt(Math.max(0, 1 - z * z));
    const angle = TAU * this.uniform();
    return new Vec3(r * Math.cos(angle), r * Math.sin(angle), z);
  }

  inSphere(): Vec3 { return this.onSphere().mul(Math.cbrt(this.uniform())); }

  cosineHemisphere(normal: Vec3): Vec3 {
    const [u, v] = this.inDisk();
    const w = Math.sqrt(Math.max(0, 1 - u * u - v * v));
    const [tangent, bitangent] = basis(normal);
    return tangent.mul(u).add(bitangent.mul(v)).add(normal.mul(w)).normalized();
  }

  inCone(axis: Vec3, cosMax: number): Vec3 {
    const cosTheta = 1 - this.uniform() * (1 - cosMax);
    const sinTheta = Math.sqrt(Math.max(0, 1 - cosTheta * cosTheta));
    const angle = TAU * this.uniform();
    const [tangent, bitangent] = basis(axis);
    return tangent.mul(sinTheta * Math.cos(angle)).add(bitangent.mul(sinTheta * Math.sin(angle))).add(axis.mul(cosTheta)).normalized();
  }
}

/** Two unit vectors perpendicular to `normal` and to each other. */
export function basis(normal: Vec3): [Vec3, Vec3] {
  const sign = normal.z >= 0 ? 1 : -1;
  const a = -1 / (sign + normal.z);
  const b = normal.x * normal.y * a;
  return [new Vec3(1 + sign * normal.x * normal.x * a, sign * b, -sign * normal.x), new Vec3(b, sign + normal.y * normal.y * a, -normal.y)];
}
