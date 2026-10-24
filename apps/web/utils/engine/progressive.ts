// Progressive preview: a first small image right away, then the preview
// size refined one ray per pixel at a time. Runs in a worker
// (`workers/scenePreview.worker.ts`), or on the page when workers are not
// available. The work is cut into short slices so that a newer request
// (the user moved a slider) takes over quickly.

import { Accumulator, buildScene } from './index';

export interface PreviewRequest {
  id: number;
  text: string;
  width: number;
  height: number;
  /** Rays per pixel to reach. */
  target: number;
  /** Start with a small, fast image (for live editing). */
  quick?: boolean;
}

export type PreviewReply =
  | { id: number; kind: 'image'; pixels: Uint8ClampedArray<ArrayBuffer>; width: number; height: number; samples: number; target: number; quick: boolean }
  | { id: number; kind: 'error'; message: string };

export async function runPreview(
  request: PreviewRequest,
  post: (reply: PreviewReply) => void,
  isCurrent: () => boolean,
  budgetMs = 30,
): Promise<void> {
  let scene;
  try {
    scene = buildScene(request.text);
  } catch (error) {
    post({ id: request.id, kind: 'error', message: error instanceof Error ? error.message : String(error) });
    return;
  }
  const stages: Accumulator[] = [];
  if (request.quick && request.width > 120) {
    const factor = 3;
    stages.push(new Accumulator(scene, Math.max(1, Math.round(request.width / factor)), Math.max(1, Math.round(request.height / factor)), 1));
  }
  stages.push(new Accumulator(scene, request.width, request.height, Math.max(1, request.target)));
  let sliceStart = performance.now();
  for (const accumulator of stages) {
    while (!accumulator.done) {
      for (let y = 0; y < accumulator.height; y += 1) {
        accumulator.rows(y, y + 1);
        if (performance.now() - sliceStart > budgetMs) {
          await new Promise<void>((resolve) => setTimeout(resolve, 0));
          if (!isCurrent()) return;
          sliceStart = performance.now();
        }
      }
      accumulator.samples += 1;
      const quick = accumulator !== stages[stages.length - 1];
      post({ id: request.id, kind: 'image', pixels: accumulator.rgba(), width: accumulator.width, height: accumulator.height, samples: accumulator.samples, target: accumulator.target, quick });
    }
  }
}
