// The AI catalogue of the BackEnd: tasks, admitted models and quotes.
import type { CatalogModel, CatalogTasks, Quote } from '~/utils/hfCatalog';
import { clientCache } from '~/services/cache';

export function useCatalog() {
  const { authorizedFetch } = useSession();

  /** The tasks of the Hub with their admitted models (cached a minute). */
  function loadTasks(force = false): Promise<CatalogTasks> {
    return clientCache.remember('catalog:tasks', () => authorizedFetch<CatalogTasks>('/catalog/tasks'), { ttl: 60_000, force });
  }

  /** Admitted models of `task`, most downloaded first. */
  function loadModels(task: string, search = '', limit = 20): Promise<{ models: CatalogModel[]; total: number }> {
    return clientCache.remember(`catalog:models:${task}:${search}:${limit}`, () => authorizedFetch<{ models: CatalogModel[]; total: number }>('/catalog/models', { query: { task, q: search || undefined, limit } }), { ttl: 30_000 });
  }

  /** The quote of `items` items with model `key` (warm or cold). */
  function loadQuote(key: string, items: number): Promise<{ quote: Quote; networkKnown: boolean }> {
    return authorizedFetch<{ quote: Quote; networkKnown: boolean }>(`/catalog/models/${encodeURIComponent(key)}/quote`, { query: { items: Math.max(1, items) } });
  }

  return { loadTasks, loadModels, loadQuote };
}
