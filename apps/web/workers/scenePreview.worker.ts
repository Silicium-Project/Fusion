// Scene preview off the main thread (see `utils/engine/progressive.ts`).
// A new request replaces the one in progress.

import { runPreview, type PreviewReply, type PreviewRequest } from '../utils/engine/progressive';

let current = 0;

addEventListener('message', (event: MessageEvent<PreviewRequest>) => {
  const request = event.data;
  current = request.id;
  void runPreview(
    request,
    (reply: PreviewReply) => postMessage(reply, reply.kind === 'image' ? { transfer: [reply.pixels.buffer] } : {}),
    () => current === request.id,
  );
});
