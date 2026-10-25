// Runs scene previews in a worker (or on the page when workers are not
// available): `render` replaces the preview in progress, replies arrive in
// `onReply` until the requested rays per pixel are reached.

import { runPreview, type PreviewReply, type PreviewRequest } from './engine/progressive';

export type { PreviewReply } from './engine/progressive';

export function createScenePreview(onReply: (reply: PreviewReply) => void) {
  let worker: Worker | undefined;
  let id = 0;
  let last: PreviewRequest | undefined;

  const onPage = (request: PreviewRequest) => {
    void runPreview(
      request,
      (reply) => {
        if (reply.id === id) onReply(reply);
      },
      () => request.id === id,
      12,
    );
  };

  try {
    worker = new Worker(new URL('../workers/scenePreview.worker.ts', import.meta.url), {
      type: 'module',
    });
    worker.onmessage = (event: MessageEvent<PreviewReply>) => {
      if (event.data.id === id) onReply(event.data);
    };
    worker.onerror = () => {
      // The worker could not start (old browser, blocked script): render on the page.
      worker?.terminate();
      worker = undefined;
      if (last && last.id === id) onPage(last);
    };
  } catch {
    worker = undefined;
  }

  return {
    render(request: Omit<PreviewRequest, 'id'>) {
      id += 1;
      last = { ...request, id };
      if (worker) worker.postMessage(last);
      else onPage(last);
    },
    stop() {
      id += 1;
      worker?.terminate();
      worker = undefined;
    },
  };
}
