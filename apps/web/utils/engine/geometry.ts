// Shapes, transforms and BVH of the preview engine (port of the raytracer's
// `engine/geometry.rs`).

import { EPSILON, Vec3 } from './math';

export type Shape =
  | { kind: 'sphere'; center: Vec3; radius: number }
  | { kind: 'plane'; point: Vec3; normal: Vec3 }
  | { kind: 'triangle'; a: Vec3; edge1: Vec3; edge2: Vec3; normal: Vec3 }
  | { kind: 'quad'; corner: Vec3; u: Vec3; v: Vec3; normal: Vec3 };

export const triangle = (a: Vec3, b: Vec3, c: Vec3): Shape => {
  const edge1 = b.sub(a);
  const edge2 = c.sub(a);
  return { kind: 'triangle', a, edge1, edge2, normal: edge1.cross(edge2).normalized() };
};

export const quad = (corner: Vec3, u: Vec3, v: Vec3): Shape => ({ kind: 'quad', corner, u, v, normal: u.cross(v).normalized() });

/** Distance and outward normal of the first hit after `EPSILON`. */
export function intersect(shape: Shape, origin: Vec3, direction: Vec3): [number, Vec3] | undefined {
  switch (shape.kind) {
    case 'sphere': {
      const offset = origin.sub(shape.center);
      const halfB = offset.dot(direction);
      const c = offset.dot(offset) - shape.radius * shape.radius;
      const discriminant = halfB * halfB - c;
      if (discriminant < 0) return undefined;
      const root = Math.sqrt(discriminant);
      const distance = -halfB - root > EPSILON ? -halfB - root : -halfB + root > EPSILON ? -halfB + root : undefined;
      if (distance === undefined) return undefined;
      const point = origin.add(direction.mul(distance));
      return [distance, point.sub(shape.center).div(shape.radius)];
    }
    case 'plane': {
      const denominator = shape.normal.dot(direction);
      if (Math.abs(denominator) < 1e-12) return undefined;
      const distance = shape.point.sub(origin).dot(shape.normal) / denominator;
      return distance > EPSILON ? [distance, shape.normal] : undefined;
    }
    case 'triangle': {
      const p = direction.cross(shape.edge2);
      const determinant = shape.edge1.dot(p);
      if (Math.abs(determinant) < 1e-12) return undefined;
      const inverse = 1 / determinant;
      const s = origin.sub(shape.a);
      const u = s.dot(p) * inverse;
      if (u < 0 || u > 1) return undefined;
      const q = s.cross(shape.edge1);
      const v = direction.dot(q) * inverse;
      if (v < 0 || u + v > 1) return undefined;
      const distance = shape.edge2.dot(q) * inverse;
      return distance > EPSILON ? [distance, shape.normal] : undefined;
    }
    case 'quad': {
      const denominator = shape.normal.dot(direction);
      if (Math.abs(denominator) < 1e-12) return undefined;
      const distance = shape.corner.sub(origin).dot(shape.normal) / denominator;
      if (distance <= EPSILON) return undefined;
      const relative = origin.add(direction.mul(distance)).sub(shape.corner);
      const n = shape.u.cross(shape.v);
      const w = n.div(n.dot(n));
      const alpha = w.dot(relative.cross(shape.v));
      const beta = w.dot(shape.u.cross(relative));
      return alpha >= 0 && alpha <= 1 && beta >= 0 && beta <= 1 ? [distance, shape.normal] : undefined;
    }
  }
}

export function area(shape: Shape): number {
  switch (shape.kind) {
    case 'sphere': return 4 * Math.PI * shape.radius * shape.radius;
    case 'plane': return Infinity;
    case 'triangle': return 0.5 * shape.edge1.cross(shape.edge2).length();
    case 'quad': return shape.u.cross(shape.v).length();
  }
}

interface Aabb { min: Vec3; max: Vec3 }

function bounds(shape: Shape): Aabb | undefined {
  const pad = 1e-6;
  const box = (points: Vec3[]): Aabb => ({
    min: new Vec3(Math.min(...points.map((p) => p.x)) - pad, Math.min(...points.map((p) => p.y)) - pad, Math.min(...points.map((p) => p.z)) - pad),
    max: new Vec3(Math.max(...points.map((p) => p.x)) + pad, Math.max(...points.map((p) => p.y)) + pad, Math.max(...points.map((p) => p.z)) + pad),
  });
  switch (shape.kind) {
    case 'sphere': {
      const r = new Vec3(shape.radius, shape.radius, shape.radius);
      return { min: shape.center.sub(r), max: shape.center.add(r) };
    }
    case 'plane': return undefined;
    case 'triangle': return box([shape.a, shape.a.add(shape.edge1), shape.a.add(shape.edge2)]);
    case 'quad': return box([shape.corner, shape.corner.add(shape.u), shape.corner.add(shape.v), shape.corner.add(shape.u).add(shape.v)]);
  }
}

function hitsBox(box: Aabb, origin: Vec3, inverse: Vec3, limit: number): boolean {
  let near = 0;
  let far = limit;
  for (let axis = 0; axis < 3; axis += 1) {
    const a = (box.min.axis(axis) - origin.axis(axis)) * inverse.axis(axis);
    const b = (box.max.axis(axis) - origin.axis(axis)) * inverse.axis(axis);
    const low = a <= b ? a : b;
    const high = a <= b ? b : a;
    if (low > near) near = low;
    if (high < far) far = high;
    if (near > far) return false;
  }
  return true;
}

/** Scale, then rotation (degrees around x, then y, then z), then translation. */
export class Transform {
  private rows: [Vec3, Vec3, Vec3];
  constructor(private scale = new Vec3(1, 1, 1), rotationDegrees = new Vec3(), private translation = new Vec3()) {
    const [ax, ay, az] = [rotationDegrees.x, rotationDegrees.y, rotationDegrees.z].map((d) => (d * Math.PI) / 180) as [number, number, number];
    const [sx, cx, sy, cy, sz, cz] = [Math.sin(ax), Math.cos(ax), Math.sin(ay), Math.cos(ay), Math.sin(az), Math.cos(az)];
    this.rows = [
      new Vec3(cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
      new Vec3(sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
      new Vec3(-sy, cy * sx, cy * cx),
    ];
  }
  private rotate(v: Vec3) { return new Vec3(this.rows[0].dot(v), this.rows[1].dot(v), this.rows[2].dot(v)); }
  point(p: Vec3) { return this.rotate(p.hadamard(this.scale)).add(this.translation); }
  vector(v: Vec3) { return this.rotate(v.hadamard(this.scale)); }
  normal(n: Vec3) { return this.rotate(new Vec3(n.x / this.scale.x, n.y / this.scale.y, n.z / this.scale.z)).normalized(); }
  uniformScale() { return Math.max(Math.abs(this.scale.x), Math.abs(this.scale.y), Math.abs(this.scale.z)); }
}

interface Node { box: Aabb; first: number; count: number; left: number; right: number }

/** Bounding-volume hierarchy over the finite shapes (same build as the engine). */
export class Bvh {
  private nodes: Node[] = [];
  private order: number[];

  constructor(private shapes: Shape[], members: number[]) {
    this.order = members;
    const boxes = shapes.map(bounds);
    if (members.length) this.split(boxes, 0, members.length);
  }

  private split(boxes: (Aabb | undefined)[], first: number, count: number): number {
    const items = this.order.slice(first, first + count);
    const centre = (i: number) => { const b = boxes[i]!; return b.min.add(b.max).mul(0.5); };
    const min = new Vec3(Infinity, Infinity, Infinity);
    const max = new Vec3(-Infinity, -Infinity, -Infinity);
    const cmin = new Vec3(Infinity, Infinity, Infinity);
    const cmax = new Vec3(-Infinity, -Infinity, -Infinity);
    for (const item of items) {
      const b = boxes[item]!;
      const c = centre(item);
      min.x = Math.min(min.x, b.min.x); min.y = Math.min(min.y, b.min.y); min.z = Math.min(min.z, b.min.z);
      max.x = Math.max(max.x, b.max.x); max.y = Math.max(max.y, b.max.y); max.z = Math.max(max.z, b.max.z);
      cmin.x = Math.min(cmin.x, c.x); cmin.y = Math.min(cmin.y, c.y); cmin.z = Math.min(cmin.z, c.z);
      cmax.x = Math.max(cmax.x, c.x); cmax.y = Math.max(cmax.y, c.y); cmax.z = Math.max(cmax.z, c.z);
    }
    const node = this.nodes.length;
    this.nodes.push({ box: { min, max }, first, count, left: 0, right: 0 });
    if (count <= 4) return node;
    const extent = cmax.sub(cmin);
    const axis = extent.x >= extent.y && extent.x >= extent.z ? 0 : extent.y >= extent.z ? 1 : 2;
    items.sort((a, b) => centre(a).axis(axis) - centre(b).axis(axis) || a - b);
    this.order.splice(first, count, ...items);
    const half = Math.floor(count / 2);
    const left = this.split(boxes, first, half);
    const right = this.split(boxes, first + half, count - half);
    Object.assign(this.nodes[node]!, { count: 0, left, right });
    return node;
  }

  /** Nearest hit: [distance, outward normal, shape index]. */
  intersect(origin: Vec3, direction: Vec3, limit: number): [number, Vec3, number] | undefined {
    if (!this.nodes.length) return undefined;
    const inverse = new Vec3(1 / direction.x, 1 / direction.y, 1 / direction.z);
    let best: [number, Vec3, number] | undefined;
    const stack = [0];
    while (stack.length) {
      const node = this.nodes[stack.pop()!]!;
      if (!hitsBox(node.box, origin, inverse, best ? best[0] : limit)) continue;
      if (node.count > 0) {
        for (let i = node.first; i < node.first + node.count; i += 1) {
          const member = this.order[i]!;
          const hit = intersect(this.shapes[member]!, origin, direction);
          if (!hit) continue;
          const better = best ? hit[0] < best[0] || (hit[0] === best[0] && member < best[2]) : hit[0] < limit;
          if (better) best = [hit[0], hit[1], member];
        }
      } else {
        stack.push(node.right, node.left);
      }
    }
    return best;
  }
}
