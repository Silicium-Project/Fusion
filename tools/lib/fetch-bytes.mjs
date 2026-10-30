/** Pinned tool downloads survive a dropped connection; a checksum mismatch is never retried. */
import { Failure } from './process.mjs';
export const downloadAttempts = 3;
const retryable = (status) => status === 408 || status === 429 || status >= 500;
export async function fetchBytes(
  url,
  {
    timeoutMs = 120_000,
    attempts = downloadAttempts,
    request = fetch,
    sleep = (ms) =>
      new Promise((done) => {
        setTimeout(done, ms);
      }),
  } = {},
) {
  let last;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const response = await request(url, { signal: AbortSignal.timeout(timeoutMs) });
      if (response.ok) return Buffer.from(await response.arrayBuffer());
      last = new Failure(`Download failed: HTTP ${response.status}`, 4);
      if (!retryable(response.status)) throw last;
    } catch (error) {
      if (error === last) throw error;
      last = new Failure(`Download failed: ${error.cause?.code ?? error.name}`, 4);
    }
    if (attempt < attempts) await sleep(2000 * attempt ** 2);
  }
  throw last;
}
