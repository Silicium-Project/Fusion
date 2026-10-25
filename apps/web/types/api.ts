import type { CollectionDocument, DocumentIndexSummary } from '~/utils/documents';
import type { BatchAIDashboard } from '~/utils/batchAI';
import type { CatalogDashboard } from '~/utils/hfCatalog';

export type JobStatus =
  'queued' | 'running' | 'cancelling' | 'completed' | 'failed' | 'cancelled' | 'expired' | string;

export interface User {
  id: number;
  email: string;
  username?: string;
  firstName?: string;
  lastName?: string;
  walletAddress?: string;
  role?: string;
  createdAt?: string;
}

export interface AuthTokens {
  token: string;
  refresh_token?: string;
}

export interface Job {
  id: number;
  userId?: number;
  title: string;
  description?: string;
  workload: string;
  priority: string;
  fragmentCount?: number;
  /** Document searches added to the same collection are searched together. */
  collectionId?: string;
  status: JobStatus;
  siliciumJobId: string;
  devnetJob?: string;
  solanaJob?: string;
  solanaExpectedFragments?: number;
  solanaCreateSignature?: string;
  solanaRefundSignature?: string;
  solanaRefunded?: boolean;
  solanaFinalizeSignature?: string;
  solanaFinalized?: boolean;
  errorMessage?: string;
  deadlineAt?: string;
  cancelRequestedAt?: string;
  cancelledAt?: string;
  cancelReason?: string;
  billableWorkUnits?: number;
  computeReceiptHash?: string;
  network?: Record<string, unknown>;
  startedAt?: string;
  completedAt?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface JobList {
  items: Job[];
  total: number;
  page: number;
  pageSize: number;
}

export interface NetworkPeer {
  node_id?: string;
  nodeId?: string;
  role?: string;
  roles?: string[];
  node_roles?: string[];
  status?: string;
  availability_status?: 'online' | 'offline' | string;
  online?: boolean;
  last_seen_unix?: number;
  last_seen_utc?: string;
  lastSeenUtc?: string;
  app_version?: string;
  release_channel?: string;
  release_build?: string;
  latest_version?: string;
  version_status?: string;
  outdated?: boolean;
  reputation?: number;
  telemetry?: NetworkRuntimeTelemetry;
  metrics?: NetworkPeerMetrics;
  activity?: {
    active_tasks?: Record<string, unknown>[];
    telemetry?: NetworkRuntimeTelemetry;
    [key: string]: unknown;
  };
  task_queue?: Record<string, unknown>[];
  [key: string]: unknown;
}

export interface NetworkRuntimeTelemetry {
  schema?: string;
  sampled_unix?: number;
  sample_interval_ms?: number;
  node_uptime_seconds?: number;
  process_cpu_percent?: number;
  process_cpu_percent_one_core?: number;
  process_cpu_seconds?: number;
  process_rss_bytes?: number;
  process_peak_rss_bytes?: number;
  system_cpu_percent?: number;
  system_memory_total_bytes?: number;
  system_memory_available_bytes?: number;
  system_memory_used_bytes?: number;
  system_memory_percent?: number;
  logical_cpu_count?: number;
  runtime_thread_count?: number;
  load_average?: number[];
  storage_total_bytes?: number;
  storage_free_bytes?: number;
  storage_used_percent?: number;
  [key: string]: unknown;
}

export interface NetworkPeerMetrics {
  updated_utc?: string;
  runtime?: NetworkRuntimeTelemetry;
  handled?: number;
  failed?: number;
  retried?: number;
  dead_lettered?: number;
  dispatched?: number;
  dispatch_failed?: number;
  [key: string]: unknown;
}

export interface NetworkMetrics {
  online_peers?: number;
  telemetry_nodes?: number;
  active_tasks?: number;
  queue_depth?: number;
  logical_cpu_count?: number;
  system_cpu_percent?: number;
  system_memory_percent?: number;
  storage_used_percent?: number;
  updated_utc?: string;
  [key: string]: unknown;
}

export interface NetworkPeersResponse {
  peers: NetworkPeer[];
  updated_utc?: string;
  metrics?: NetworkMetrics;
  release_channels?: Record<string, unknown>;
  release_manifest_generated_utc?: string;
  [key: string]: unknown;
}

export interface NetworkSubtask {
  task_id?: string;
  taskId?: string;
  status?: string;
  handled_by?: string;
  handledBy?: string;
  /** Task-book author id of the worker (Rust node). */
  worker?: string;
  fragment_index?: number;
  fragmentIndex?: number;
  stage?: string;
  error?: string;
  error_message?: string;
  errorType?: string;
  error_type?: string;
  traceback?: string;
  error_traceback?: string;
  failureDetail?: string;
  failure_detail?: string;
  [key: string]: unknown;
}

export interface NetworkWorkload {
  work_id: string;
  emitter_node_id?: string;
  workload?: string;
  kind?: string;
  status: JobStatus;
  total: number;
  completed: number;
  failed: number;
  active: number;
  progress_percent?: number;
  updated_at?: string;
  error?: string;
  failure_detail?: string;
  errorType?: string;
  traceback?: string;
  failureDetail?: string;
  subtasks?: NetworkSubtask[];
}

export interface NetworkTasksResponse {
  active: Record<string, unknown>[];
  recent: Record<string, unknown>[];
  workloads: NetworkWorkload[];
  emitter_node_id?: string;
  queue?: {
    queued: number;
    oldest_wait_seconds?: number;
    online_compute_workers?: number;
    compatible_workers?: number;
    workloads?: string[];
    reason?:
      | 'no_compute_workers'
      | 'no_compatible_workers'
      | 'workers_not_claiming'
      | 'network_state_unavailable'
      | 'mixed_workload_blockers'
      | string;
    workload_diagnostics?: NetworkQueueWorkloadDiagnostic[];
  };
}

export interface NetworkQueueWorkloadDiagnostic {
  workload: string;
  queued: number;
  oldest_wait_seconds?: number;
  online_compute_workers?: number;
  compatible_workers?: number;
  reason?: string;
}

export interface JobVerifierTrace {
  author?: string;
  verdict?: boolean | null;
  verification_event?: string;
  self_verification?: boolean;
}

export interface JobTaskTrace {
  worker?: string;
  verifiers?: JobVerifierTrace[];
  attempt?: number;
  finalized?: boolean;
}

export interface JobFragment {
  fragment_index?: number;
  fragmentIndex?: number;
  status?: string;
  stage?: string;
  handled_by?: string;
  handledBy?: string;
  /** Task-book author id of the worker (Rust node). */
  worker?: string;
  /** Signed compute and verification participants for this attempt. */
  trace?: JobTaskTrace;
  x_start?: number;
  x_end?: number;
  y_start?: number;
  y_end?: number;
  performance?: JobPerformance;
  verify_performance?: JobPerformance;
  [key: string]: unknown;
}

export interface JobPerformance {
  schema?: string;
  total_ms?: number;
  compute_ms?: number;
  compute_work_ms?: number;
  verification_ms?: number;
  network_ms?: number;
  overhead_ms?: number;
  worker_overhead_ms?: number;
  compute_to_total_ratio?: number | null;
  compute_to_network_ratio?: number | null;
  parallelism_factor?: number | null;
  measured_compute_tasks?: number;
  measured_verify_tasks?: number;
  [key: string]: unknown;
}

export interface JobDashboard {
  job: Job;
  resultReady: boolean;
  resultUrl: string;
  /** Documents read and files skipped, once a document search is finished. */
  documentIndex?: DocumentIndexSummary;
  /** Every document a search of this job covers (the whole collection). */
  collectionDocuments?: CollectionDocument[] | null;
  /** The request of a batch AI job and, once done, its model and counts. */
  batchAI?: BatchAIDashboard;
  /** A job of the AI catalogue (`ai/hf/…`). */
  hf?: CatalogDashboard;
  diagnostics?: Record<string, unknown>;
  summary?: {
    success?: boolean;
    progress?: number;
    stage?: string;
    updatedUtc?: string;
    error?: string;
    errorType?: string;
    traceback?: string;
    failureDetail?: string;
    fragmentCount?: number;
    finalHash?: string;
    reassembledHash?: string;
    expectedFullHash?: string;
    image?: { width?: number; height?: number };
    network?: Record<string, unknown>;
    fragments?: JobFragment[];
    nodeRuns?: Record<string, unknown>[];
    performance?: JobPerformance;
    splitTree?: unknown;
    [key: string]: unknown;
  };
  devnet?: ChainTrace;
}

/** A verifier of an anchored task (task-book author id = hex Ed25519 key). */
export interface ChainVerifier {
  author: string;
  verdict: boolean | null;
  verification_event: string;
  self_verification: boolean;
}

/** One sibling on a Merkle path. */
export interface ChainProofStep {
  sibling: string;
  left: boolean;
}

/** A task of an anchored job: its signed trace, leaf hash and Merkle proof. */
export interface ChainTask {
  task_id: string;
  fragment_index: number;
  status: string;
  result_sha256: string;
  publisher: string;
  proposal_event: string;
  spec_sha256: string;
  attempt: number;
  worker: string;
  claim_event: string;
  result_event: string;
  verifiers: ChainVerifier[];
  leaf_hash: string;
  proof: ChainProofStep[];
}

/** Blockchain trace of a job (`devnet` block of the dashboard). */
export interface ChainTrace {
  enabled?: boolean;
  ok?: boolean;
  /** `anchored`, `pending`, `failed` or `not_requested`. */
  status?: string;
  job?: string;
  programId?: string;
  rpc?: string;
  cluster?: string;
  payer?: string;
  signatures?: string[];
  explorerUrl?: string;
  memo?: string;
  merkleRoot?: string;
  finalSha256?: string;
  taskCount?: number;
  fragments?: ChainTask[];
  splitTree?: unknown;
  updatedUtc?: string;
  error?: string;
  [key: string]: unknown;
}

export interface SystemStatus {
  status: 'operational' | 'degraded' | 'unavailable' | string;
  checkedAt: string;
  release?: {
    release_channel?: 'dev' | 'prod' | string;
    release_version?: string;
    release_build?: string;
  };
  backend: { status: string; database?: string };
  network: {
    status: string;
    peers: number;
    activePeers: number;
    outdatedPeers: number;
    telemetryNodes?: number;
    activeTasks?: number;
    queueDepth?: number;
    knownTasks?: number;
    logicalCpuCount?: number;
    systemCpuPercent?: number;
    systemMemoryPercent?: number;
    storageUsedPercent?: number;
    updatedAt?: string;
  };
  blockchain: { status: string; network: string; configured: boolean; programId?: string };
}

export interface WalletChallenge {
  challenge: string;
  message: string;
  expiresAt: string;
}

export interface UpdateRelease {
  version?: string;
  build?: string;
  url?: string;
  sha256?: string;
  signature?: string;
  generated_utc?: string;
  [key: string]: unknown;
}

export interface UpdateManifest {
  generated_utc?: string;
  channels?: Record<string, UpdateRelease>;
}
