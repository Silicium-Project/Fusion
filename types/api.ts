export type JobStatus = 'queued' | 'running' | 'cancelling' | 'completed' | 'failed' | 'cancelled' | 'expired' | string;

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
  status: JobStatus;
  siliciumJobId: string;
  dashboardUrl?: string;
  devnetJob?: string;
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
  activity?: { active_tasks?: Record<string, unknown>[]; telemetry?: NetworkRuntimeTelemetry; [key: string]: unknown };
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
  python_thread_count?: number;
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
}

export interface JobFragment {
  fragment_index?: number;
  fragmentIndex?: number;
  status?: string;
  stage?: string;
  handled_by?: string;
  handledBy?: string;
  x_start?: number;
  x_end?: number;
  y_start?: number;
  y_end?: number;
  [key: string]: unknown;
}

export interface JobDashboard {
  job: Job;
  resultReady: boolean;
  resultUrl: string;
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
    splitTree?: unknown;
    [key: string]: unknown;
  };
  devnet?: {
    enabled?: boolean;
    ok?: boolean;
    status?: string;
    job?: string;
    programId?: string;
    rpc?: string;
    signatures?: string[];
    fragments?: unknown;
    splitTree?: unknown;
    [key: string]: unknown;
  };
}

export interface SystemStatus {
  status: 'operational' | 'degraded' | 'unavailable' | string;
  checkedAt: string;
  backend: { status: string; database?: string };
  network: {
    status: string;
    peers: number;
    activePeers: number;
    outdatedPeers: number;
    telemetryNodes?: number;
    activeTasks?: number;
    queueDepth?: number;
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
