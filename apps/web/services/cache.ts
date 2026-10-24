export interface CacheOptions {
  ttl?: number;
  force?: boolean;
}

interface CacheEntry<T> {
  value: T;
  expiresAt: number;
}

export class MemoryCache {
  private entries = new Map<string, CacheEntry<unknown>>();
  private pending = new Map<string, Promise<unknown>>();

  async remember<T>(key: string, loader: () => Promise<T>, options: CacheOptions = {}): Promise<T> {
    const cached = this.entries.get(key) as CacheEntry<T> | undefined;
    if (!options.force && cached && cached.expiresAt > Date.now()) return cached.value;

    const running = this.pending.get(key) as Promise<T> | undefined;
    if (!options.force && running) return running;

    const request = loader()
      .then((value) => {
        this.entries.set(key, { value, expiresAt: Date.now() + Math.max(0, options.ttl ?? 15_000) });
        return value;
      })
      .finally(() => this.pending.delete(key));

    this.pending.set(key, request);
    return request;
  }

  invalidate(prefix?: string): void {
    if (!prefix) {
      this.entries.clear();
      this.pending.clear();
      return;
    }
    for (const key of this.entries.keys()) if (key.startsWith(prefix)) this.entries.delete(key);
    for (const key of this.pending.keys()) if (key.startsWith(prefix)) this.pending.delete(key);
  }

  size(): number {
    return this.entries.size;
  }
}

export const clientCache = new MemoryCache();
