import type { Job, JobDashboard, JobList } from '~/types/api';
import { clientCache } from '~/services/cache';

export interface CreateJobInput {
  title: string;
  description: string;
  workload: string;
  priority: string;
  fragmentCount: number;
  maxRuntimeSeconds: number;
  file: File;
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
    form.append('fragment_count', String(input.fragmentCount));
    form.append('max_runtime_seconds', String(input.maxRuntimeSeconds));
    form.append('file', input.file);
    const job = await authorizedFetch<Job>('/jobs', { method: 'POST', body: form, timeout: 30_000 });
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
    link.download = `${job.title || 'silicium-resultat'}-${job.id}.${blob.type.includes('png') ? 'png' : 'bin'}`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return { jobs, total, loading, error, loadJobs, getJobDashboard, createJob, cancelJob, downloadResult };
}
