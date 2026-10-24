// Preview engine: a TypeScript port of the network's raytracer (engine 2),
// used by the scene editor to show what the network will render. Same
// shapes, materials, lights, camera and lighting modes; its random numbers
// differ, so a noisy preview is not the same noise as the final image.

import { cameraRay, firstShape, sampleColor, toByte } from './integrator';
import { buildScene, type Scene } from './scene';

export { buildScene, type Scene } from './scene';

/** Accumulates samples of a scene drawn at `width` × `height` (any size, same framing). */
export class Accumulator {
  readonly sum: Float64Array;
  samples = 0;

  constructor(readonly scene: Scene, readonly width: number, readonly height: number, readonly target = scene.settings.samples) {
    this.sum = new Float64Array(width * height * 3);
  }

  get done() { return this.samples >= this.target; }

  /** Adds one sample to rows `from` … `to` − 1 (a pass is complete once every row got it). */
  rows(from: number, to: number) {
    const { scene, width, height, sum, samples, target } = this;
    for (let y = from; y < to; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const color = sampleColor(scene, x, y, width, height, samples, Math.max(1, target));
        const at = (y * width + x) * 3;
        sum[at] += color.x;
        sum[at + 1] += color.y;
        sum[at + 2] += color.z;
      }
    }
  }

  /** One full sample on every pixel. */
  pass() {
    this.rows(0, this.height);
    this.samples += 1;
  }

  rgba(): Uint8ClampedArray<ArrayBuffer> {
    const pixels = new Uint8ClampedArray(new ArrayBuffer(this.width * this.height * 4));
    const count = Math.max(1, this.samples);
    for (let i = 0, j = 0; i < this.sum.length; i += 3, j += 4) {
      pixels[j] = toByte(this.scene, this.sum[i]! / count);
      pixels[j + 1] = toByte(this.scene, this.sum[i + 1]! / count);
      pixels[j + 2] = toByte(this.scene, this.sum[i + 2]! / count);
      pixels[j + 3] = 255;
    }
    return pixels;
  }
}

/** RGBA pixels of a scene text with `samples` rays per pixel (synchronous: small images only). */
export function renderText(text: string, width: number, height: number, samples = 1): Uint8ClampedArray<ArrayBuffer> {
  const scene = buildScene(text);
  const accumulator = new Accumulator(scene, width, height, samples);
  while (!accumulator.done) accumulator.pass();
  return accumulator.rgba();
}

/** Index of the shape under (`u`, `v`) (0–1 across the image), if any. */
export function pickShape(scene: Scene, u: number, v: number): number | undefined {
  const [origin, direction] = cameraRay(scene, u * scene.width, v * scene.height, scene.width, scene.height);
  return firstShape(scene, origin, direction);
}

/** Largest size that fits `maxWidth` × `maxHeight` with the scene's aspect ratio. */
export function previewSize(scene: { width: number; height: number }, maxWidth: number, maxHeight = maxWidth): { width: number; height: number } {
  const ratio = Math.min(maxWidth / scene.width, maxHeight / scene.height, 1);
  return { width: Math.max(1, Math.round(scene.width * ratio)), height: Math.max(1, Math.round(scene.height * ratio)) };
}
