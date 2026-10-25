import { describe, expect, it, vi } from 'vitest';
import { MemoryCache } from '../services/cache';

describe('client cache', () => {
  it('deduplicates concurrent requests and keeps the resolved value until expiry', async () => {
    const cache = new MemoryCache();
    const loader = vi.fn(async () => ({ value: Math.random() }));
    const [first, second] = await Promise.all([
      cache.remember('network', loader, { ttl: 1_000 }),
      cache.remember('network', loader, { ttl: 1_000 }),
    ]);
    expect(first).toEqual(second);
    expect(loader).toHaveBeenCalledTimes(1);
    expect(await cache.remember('network', loader, { ttl: 1_000 })).toEqual(first);
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it('supports scoped invalidation and forced refreshes', async () => {
    const cache = new MemoryCache();
    let version = 0;
    await cache.remember('jobs:1', async () => ++version);
    await cache.remember('network:1', async () => ++version);
    cache.invalidate('jobs:');
    expect(await cache.remember('jobs:1', async () => ++version)).toBe(3);
    expect(await cache.remember('network:1', async () => ++version)).toBe(2);
    expect(await cache.remember('network:1', async () => ++version, { force: true })).toBe(4);
  });
});
