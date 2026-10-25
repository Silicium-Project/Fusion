import { extractJobError, isHashWorkload, resultExtension } from '~/utils/jobs';
import { isDocumentSearchWorkload, type DocumentHit } from '~/utils/documents';
import { isBatchAIWorkload, type BatchAnswersPage } from '~/utils/batchAI';
import { isHFWorkload } from '~/utils/hfCatalog';
import type { Job, JobDashboard, JobList } from '~/types/api';
import { clientCache } from '~/services/cache';
import { translate } from '~/utils/i18n';
import { phantomProvider } from '~/utils/wallet';
import { resolveSolanaRpcEndpoint } from '~/utils/solanaRpc';

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
  constructor() {
    super(translate('errors.searchPreparing'));
  }
}

function isSolanaRpcRateLimitFailure(failure: unknown): boolean {
  const error = failure as { message?: unknown; code?: unknown };
  return /SOLANA_RPC_RATE_LIMITED|429|too many requests|rate limit/i.test(
    [error?.message, error?.code]
      .filter((value) => value !== undefined && value !== null)
      .join(' '),
  );
}

function isSolanaBlockhashFailure(failure: unknown): boolean {
  const error = failure as { message?: unknown; cause?: { message?: unknown }; logs?: unknown };
  const logs = Array.isArray(error?.logs)
    ? error.logs.filter((line) => typeof line === 'string')
    : [];
  return /SOLANA_BLOCKHASH_EXPIRED|blockhash not found|block height exceeded|blockhash expired/i.test(
    [error?.message, error?.cause?.message, ...logs]
      .filter((value) => value !== undefined && value !== null)
      .join('\n'),
  );
}

/** A file name from a project title: no path separators or reserved characters. */
const safeDownloadName = (title: string): string =>
  (title || 'silicium-result')
    .replace(/[\\/:*?"<>|\u0000-\u001f]+/g, '_')
    .trim()
    .slice(0, 80) || 'silicium-result';

export function useJobs() {
  const { authorizedFetch, authorizedFetchRaw, ensureAccessToken, user } = useSession();
  const walletState = useWallet();
  const jobs = useState<Job[]>('jobs:items', () => []);
  const total = useState<number>('jobs:total', () => 0);
  const loading = useState<boolean>('jobs:loading', () => false);
  const error = useState<string>('jobs:error', () => '');

  const identity = () => String(user.value?.id || 'current');

  async function loadJobs(
    page = 1,
    pageSize = 20,
    status = 'all',
    force = false,
  ): Promise<JobList> {
    loading.value = true;
    error.value = '';
    const key = `jobs:${identity()}:${page}:${pageSize}:${status}`;
    try {
      const result = await clientCache.remember(
        key,
        async () => {
          const response = await authorizedFetchRaw<Job[]>('/jobs', {
            query: { page, page_size: pageSize, ...(status !== 'all' ? { status } : {}) },
          });
          return {
            items: response._data || [],
            total: Number(response.headers.get('x-total-count') || response._data?.length || 0),
            page: Number(response.headers.get('x-page') || page),
            pageSize: Number(response.headers.get('x-page-size') || pageSize),
          } satisfies JobList;
        },
        { ttl: 8_000, force },
      );
      jobs.value = result.items;
      total.value = result.total;
      return result;
    } catch (failure) {
      error.value = translate('errors.jobsLoad');
      throw failure;
    } finally {
      loading.value = false;
    }
  }

  async function getJobDashboard(id: string | number, force = false): Promise<JobDashboard> {
    return clientCache.remember(
      `job:${identity()}:${id}`,
      () => authorizedFetch<JobDashboard>(`/jobs/${id}/dashboard`),
      { ttl: 4_000, force },
    );
  }

  async function createJob(input: CreateJobInput): Promise<Job> {
    const runtime = useRuntimeConfig();
    let payment: { jobAddress: string; signature: string; expectedFragments: number } | null = null;
    if (Boolean(runtime.public.solanaPaymentsEnabled)) {
      if (!isHashWorkload(input.workload) || !input.file)
        throw new Error(translate('jobForm.paymentHashOnly'));
      if (!user.value?.walletAddress) throw new Error(translate('jobForm.paymentWalletRequired'));
      if (!import.meta.client) throw new Error(translate('jobForm.paymentBrowserRequired'));
      const provider = phantomProvider(window);
      if (!provider?.signTransaction) throw new Error(translate('jobForm.paymentPhantomRequired'));
      const connected = await provider.connect();
      if (connected.publicKey.toString() !== user.value.walletAddress)
        throw new Error(translate('jobForm.paymentWalletMismatch'));
      const [{ Connection }, { createSILEscrow }] = await Promise.all([
        import('@solana/web3.js'),
        import('~/utils/solanaJobs'),
      ]);
      const expectedFragments = Math.min(
        256,
        Math.max(1, Math.trunc(input.fragmentCount)),
        Math.max(1, input.file.size),
      );
      const deadlineUnix =
        Math.floor(Date.now() / 1000) +
        Math.min(7 * 24 * 60 * 60, Math.max(600, input.maxRuntimeSeconds + 120));
      let escrow: Awaited<ReturnType<typeof createSILEscrow>>;
      try {
        escrow = await createSILEscrow(
          new Connection(resolveSolanaRpcEndpoint(runtime.public.solanaRpc), 'confirmed'),
          provider,
          user.value.walletAddress,
          expectedFragments,
          deadlineUnix,
          String(runtime.public.silMint || 'F5zPejtGPm2eqG1hwFGof6uWVJ79LDKeKYDVifXqhPRP'),
        );
      } catch (failure) {
        if (isSolanaRpcRateLimitFailure(failure))
          throw new Error(translate('jobForm.paymentRpcRateLimited'));
        if (isSolanaBlockhashFailure(failure))
          throw new Error(translate('jobForm.paymentBlockhashExpired'));
        throw failure;
      }
      payment = { ...escrow, expectedFragments };
    }
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
    } else if (isBatchAIWorkload(input.workload) || isHFWorkload(input.workload)) {
      // The request (`request.json`) is built in the browser; the network
      // splits the list itself.
      if (input.file) form.append('file', input.file);
      form.append('acknowledge_sharing', input.acknowledgeSharing ? '1' : '0');
    } else {
      form.append('fragment_count', String(input.fragmentCount));
      if (input.file) form.append('file', input.file);
    }
    if (payment) {
      form.append('solana_job', payment.jobAddress);
      form.append('solana_expected_fragments', String(payment.expectedFragments));
      form.append('solana_create_signature', payment.signature);
    }
    // Documents can weigh 64 Mo: leave time for slow uploads.
    let job: Job;
    try {
      job = await authorizedFetch<Job>('/jobs', {
        method: 'POST',
        body: form,
        timeout:
          isDocumentSearchWorkload(input.workload) ||
          isBatchAIWorkload(input.workload) ||
          isHFWorkload(input.workload)
            ? 300_000
            : 30_000,
      });
    } catch (failure) {
      if (payment && import.meta.client) {
        const status = Number(
          (failure as { statusCode?: unknown; status?: unknown })?.statusCode ||
            (failure as { status?: unknown })?.status ||
            0,
        );
        if (status > 0 && status < 502) {
          try {
            const provider = phantomProvider(window);
            if (provider?.signTransaction && user.value?.walletAddress) {
              const [{ Connection }, { cancelSILEscrow }] = await Promise.all([
                import('@solana/web3.js'),
                import('~/utils/solanaJobs'),
              ]);
              await provider.connect();
              await cancelSILEscrow(
                new Connection(resolveSolanaRpcEndpoint(runtime.public.solanaRpc), 'confirmed'),
                provider,
                user.value.walletAddress,
                payment.jobAddress,
                payment.expectedFragments,
              );
              await walletState.loadBalance(user.value.walletAddress);
            }
          } catch {
            throw new Error(
              `${extractJobError(failure)} ${translate('jobForm.paymentRefundRecovery', { job: payment.jobAddress })}`,
            );
          }
        } else {
          const possibleJob = await authorizedFetchRaw<Job[]>('/jobs', {
            query: { page: 1, page_size: 100 },
          }).catch(() => null);
          if (
            !possibleJob ||
            (possibleJob._data || []).some((item: Job) => item.solanaJob === payment!.jobAddress)
          ) {
            throw new Error(
              `${extractJobError(failure)} ${translate('jobForm.paymentSubmissionCheck', { job: payment.jobAddress })}`,
            );
          }
        }
      }
      throw failure;
    }
    if (payment && user.value?.walletAddress)
      await walletState.loadBalance(user.value.walletAddress);
    clientCache.invalidate('jobs:');
    return job;
  }

  async function cancelJob(id: number, reason = translate('errors.cancelReason')): Promise<Job> {
    const existing = await authorizedFetch<Job>(`/jobs/${id}`);
    let solanaRefundSignature = '';
    if (existing.solanaJob && existing.solanaExpectedFragments && !existing.solanaRefunded) {
      if (!user.value?.walletAddress || !import.meta.client)
        throw new Error(translate('jobForm.paymentWalletRequired'));
      const provider = phantomProvider(window);
      if (!provider?.signTransaction) throw new Error(translate('jobForm.paymentPhantomRequired'));
      await provider.connect();
      const runtime = useRuntimeConfig();
      const [{ Connection }, { cancelSILEscrow }] = await Promise.all([
        import('@solana/web3.js'),
        import('~/utils/solanaJobs'),
      ]);
      let signature: string | null;
      try {
        signature = await cancelSILEscrow(
          new Connection(resolveSolanaRpcEndpoint(runtime.public.solanaRpc), 'confirmed'),
          provider,
          user.value.walletAddress,
          existing.solanaJob,
          existing.solanaExpectedFragments,
        );
      } catch (failure) {
        if (isSolanaRpcRateLimitFailure(failure))
          throw new Error(translate('jobForm.paymentRpcRateLimited'));
        if (isSolanaBlockhashFailure(failure))
          throw new Error(translate('jobForm.paymentBlockhashExpired'));
        throw failure;
      }
      solanaRefundSignature = signature || '';
      await walletState.loadBalance(user.value.walletAddress);
    }
    const job = await authorizedFetch<Job>(`/jobs/${id}/cancel`, {
      method: 'POST',
      body: {
        reason,
        ...(solanaRefundSignature ? { solana_refund_signature: solanaRefundSignature } : {}),
      },
    });
    clientCache.invalidate('jobs:');
    clientCache.invalidate(`job:${identity()}:${id}`);
    return job;
  }

  async function finalizeJob(id: number, resultHash: string): Promise<Job> {
    const existing = await authorizedFetch<Job>(`/jobs/${id}`);
    if (!existing.solanaJob || !existing.solanaExpectedFragments)
      throw new Error(translate('jobForm.paymentJobMissing'));
    if (existing.solanaFinalized) return existing;
    if (!user.value?.walletAddress || !import.meta.client)
      throw new Error(translate('jobForm.paymentWalletRequired'));
    const provider = phantomProvider(window);
    if (!provider?.signTransaction) throw new Error(translate('jobForm.paymentPhantomRequired'));
    await provider.connect();
    const runtime = useRuntimeConfig();
    const [{ Connection }, { finalizeSILEscrow }] = await Promise.all([
      import('@solana/web3.js'),
      import('~/utils/solanaJobs'),
    ]);
    let signature: string | null;
    try {
      signature = await finalizeSILEscrow(
        new Connection(resolveSolanaRpcEndpoint(runtime.public.solanaRpc), 'confirmed'),
        provider,
        user.value.walletAddress,
        existing.solanaJob,
        existing.solanaExpectedFragments,
        resultHash,
      );
    } catch (failure) {
      if (isSolanaRpcRateLimitFailure(failure))
        throw new Error(translate('jobForm.paymentRpcRateLimited'));
      if (isSolanaBlockhashFailure(failure))
        throw new Error(translate('jobForm.paymentBlockhashExpired'));
      throw failure;
    }
    const job = await authorizedFetch<Job>(`/jobs/${id}/finalize`, {
      method: 'POST',
      body: signature ? { signature } : {},
    });
    await walletState.loadBalance(user.value.walletAddress);
    clientCache.invalidate('jobs:');
    clientCache.invalidate(`job:${identity()}:${id}`);
    return job;
  }

  /** Downloads the result; `format` picks one of the formats a job offers (`jsonl` for batch AI answers). */
  async function downloadResult(job: Job, format?: string): Promise<void> {
    const token = await ensureAccessToken();
    if (!token) throw new Error(translate('common.sessionExpired'));
    const config = useRuntimeConfig();
    const query = format ? `?format=${encodeURIComponent(format)}` : '';
    const response = await fetch(`${config.public.apiBase}/jobs/${job.id}/result${query}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error(translate('errors.resultUnavailable'));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${safeDownloadName(job.title)}-${job.id}.${resultExtension(blob.type, response.headers.get('content-disposition'))}`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /** A page of the answers of a batch AI job (verified ones while it runs). */
  async function loadAnswers(id: number, offset = 0, limit = 50): Promise<BatchAnswersPage> {
    return authorizedFetch<BatchAnswersPage>(`/jobs/${id}/answers`, { query: { offset, limit } });
  }

  /** The passages of the job's collection closest to `query`, best first. */
  async function searchDocuments(id: number, query: string, limit = 10): Promise<DocumentHit[]> {
    try {
      const response = await authorizedFetch<{ hits: DocumentHit[] }>(`/jobs/${id}/search`, {
        query: { q: query, k: limit },
        timeout: 40_000,
      });
      return response.hits || [];
    } catch (failure) {
      const status =
        (failure as { status?: number; statusCode?: number }).status ??
        (failure as { statusCode?: number }).statusCode;
      if (status === 503) throw new SearchPreparingError();
      throw failure;
    }
  }

  /** Opens a document of a search result in a new tab, at its page. */
  async function openDocument(
    hit: Pick<DocumentHit, 'jobId' | 'document' | 'page'>,
  ): Promise<void> {
    // Opened before the download so that the browser does not block it.
    const opened = window.open('', '_blank');
    const token = await ensureAccessToken();
    if (!token) {
      opened?.close();
      throw new Error(translate('common.sessionExpired'));
    }
    const config = useRuntimeConfig();
    const response = await fetch(
      `${config.public.apiBase}/jobs/${hit.jobId}/documents?name=${encodeURIComponent(hit.document)}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (!response.ok) {
      opened?.close();
      throw new Error(translate('errors.documentUnavailable'));
    }
    const url = URL.createObjectURL(await response.blob());
    const target = hit.page ? `${url}#page=${hit.page}` : url;
    if (opened) opened.location.href = target;
    else window.open(target, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  return {
    jobs,
    total,
    loading,
    error,
    loadJobs,
    getJobDashboard,
    createJob,
    cancelJob,
    finalizeJob,
    downloadResult,
    loadAnswers,
    searchDocuments,
    openDocument,
  };
}
