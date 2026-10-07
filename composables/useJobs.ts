import { resultExtension } from '~/utils/jobs';
import { isDocumentSearchWorkload, type DocumentHit } from '~/utils/documents';
import type { Job, JobDashboard, JobList } from '~/types/api';
import { clientCache } from '~/services/cache';

export interface CreateJobInput {
  title: string;
  description: string;
  workload: string;
  priority: string;
  fragmentCount: number;
  maxRuntimeSeconds: number;
  /** The input of a render or a hash. */
  file?: File | null;
  /** The documents of a document search. */
  files?: File[];
  /** The user confirmed that the machines of the network read the documents. */
  acknowledgeSharing?: boolean;
  /** Collection to add the documents to (a new one when empty). */
  collectionId?: string;
}

/** The search engine is still getting ready: try again in a few seconds. */
export class SearchPreparingError extends Error {
  constructor() { super('Le moteur de recherche se prépare, réessaie dans quelques secondes.'); }
}

export function useJobs() {
  const { authorizedFetch, authorizedFetchRaw, user } = useSession();
  const jobs = useState<Job[]>('jobs:items', () => []);
  const total = useState<number>('jobs:total', () => 0);
  const loading = useState<boolean>('jobs:loading', () => false);
  const error = useState<string>('jobs:error', () => '');

  const identity = () => String(user.value?.id || 'current');

  async function loadJobs(page = 1, pageSize = 20, status = 'all', force = false): Promise<JobList> {
    loading.value = true;
    error.value = '';
    const key = `jobs:${identity()}:${page}:${pageSize}:${status}`;
    try {
      const result = await clientCache.remember(key, async () => {
        const response = await authorizedFetchRaw<Job[]>('/jobs', {
          query: { page, page_size: pageSize, ...(status !== 'all' ? { status } : {}) },
        });
        return {
          items: response._data || [],
          total: Number(response.headers.get('x-total-count') || response._data?.length || 0),
          page: Number(response.headers.get('x-page') || page),
          pageSize: Number(response.headers.get('x-page-size') || pageSize),
        } satisfies JobList;
      }, { ttl: 8_000, force });
      jobs.value = result.items;
      total.value = result.total;
      return result;
    } catch (failure) {
      error.value = 'Les tâches ne peuvent pas être chargées pour le moment.';
      throw failure;
    } finally {
      loading.value = false;
    }
  }

  async function getJobDashboard(id: string | number, force = false): Promise<JobDashboard> {
    return clientCache.remember(`job:${identity()}:${id}`, () => authorizedFetch<JobDashboard>(`/jobs/${id}/dashboard`), { ttl: 4_000, force });
  }

  async function createJob(input: CreateJobInput): Promise<Job> {
    const form = new FormData();
    form.append('title', input.title.trim());
    form.append('description', input.description.trim());
    form.append('workload', input.workload);
    form.append('priority', input.priority);
    form.append('max_runtime_seconds', String(input.maxRuntimeSeconds));
    if (isDocumentSearchWorkload(input.workload)) {
      // The node splits documents itself: no part count.
      for (const document of input.files || []) form.append('files', document);
      form.append('acknowledge_sharing', input.acknowledgeSharing ? '1' : '0');
      if (input.collectionId) form.append('collection_id', input.collectionId);
    } else {
      form.append('fragment_count', String(input.fragmentCount));
      if (input.file) form.append('file', input.file);
    }
    // Documents can weigh 64 Mo: leave time for slow uploads.
    const job = await authorizedFetch<Job>('/jobs', { method: 'POST', body: form, timeout: isDocumentSearchWorkload(input.workload) ? 300_000 : 30_000 });
    clientCache.invalidate('jobs:');
    return job;
  }

  async function cancelJob(id: number, reason = 'Arrêt demandé depuis le site'): Promise<Job> {
    const job = await authorizedFetch<Job>(`/jobs/${id}/cancel`, { method: 'POST', body: { reason } });
    clientCache.invalidate('jobs:');
    clientCache.invalidate(`job:${identity()}:${id}`);
    return job;
  }

  async function downloadResult(job: Job): Promise<void> {
    const token = await useSession().ensureAccessToken();
    if (!token) throw new Error('Session expirée.');
    const config = useRuntimeConfig();
    const response = await fetch(`${config.public.apiBase}/jobs/${job.id}/result`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new Error('Le résultat n’est pas disponible.');
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${job.title || 'silicium-resultat'}-${job.id}.${resultExtension(blob.type)}`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /** The passages of the job's collection closest to `query`, best first. */
  async function searchDocuments(id: number, query: string, limit = 10): Promise<DocumentHit[]> {
    try {
      const response = await authorizedFetch<{ hits: DocumentHit[] }>(`/jobs/${id}/search`, { query: { q: query, k: limit }, timeout: 40_000 });
      return response.hits || [];
    } catch (failure) {
      const status = (failure as { status?: number; statusCode?: number }).status ?? (failure as { statusCode?: number }).statusCode;
      if (status === 503) throw new SearchPreparingError();
      throw failure;
    }
  }

  /** Opens a document of a search result in a new tab, at its page. */
  async function openDocument(hit: Pick<DocumentHit, 'jobId' | 'document' | 'page'>): Promise<void> {
    // Opened before the download so that the browser does not block it.
    const opened = window.open('', '_blank');
    const token = await useSession().ensureAccessToken();
    if (!token) { opened?.close(); throw new Error('Session expirée.'); }
    const config = useRuntimeConfig();
    const response = await fetch(`${config.public.apiBase}/jobs/${hit.jobId}/documents?name=${encodeURIComponent(hit.document)}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) { opened?.close(); throw new Error('Le document n’est pas disponible.'); }
    const url = URL.createObjectURL(await response.blob());
    const target = hit.page ? `${url}#page=${hit.page}` : url;
    if (opened) opened.location.href = target; else window.open(target, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  return { jobs, total, loading, error, loadJobs, getJobDashboard, createJob, cancelJob, downloadResult, searchDocuments, openDocument };
}
