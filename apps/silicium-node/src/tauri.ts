import { invoke } from '@tauri-apps/api/core';

export type NodeConfig = {
  repoRoot: string;
  orchestratorUrl: string;
  advertiseHost: string;
  nodeId: string;
  reputationScore: number;
};

export type NodeStatus = {
  running: boolean;
  roles: string;
};

export type CheckItem = {
  name: string;
  ok: boolean;
  detail: string;
};

export type HistoryItem = {
  name: string;
  modifiedAt: number;
  sizeBytes: number;
  kind: string;
  itemId: string;
  role: string;
  activity: string;
  fragmentIndex: string;
  ok?: boolean | null;
  peerId: string;
};

export type RuntimeTelemetry = {
  sampledUnix: number;
  sampleIntervalMs: number;
  nodeUptimeSeconds: number;
  processCpuPercent: number;
  processCpuPercentOneCore: number;
  processCpuSeconds: number;
  processRssBytes: number;
  processPeakRssBytes: number;
  systemCpuPercent: number;
  systemMemoryTotalBytes: number;
  systemMemoryAvailableBytes: number;
  systemMemoryUsedBytes: number;
  systemMemoryPercent: number;
  logicalCpuCount: number;
  pythonThreadCount: number;
  loadAverage: number[];
  storageTotalBytes: number;
  storageFreeBytes: number;
  storageUsedPercent: number;
};

export type MachineTaskActivity = {
  itemId: string;
  role: string;
  activity: string;
  workload: string;
  fragmentIndex: string;
  fragmentCount: string;
  sourceTaskId: string;
  sourceNodeId: string;
  bounds: string;
  phase: string;
  progressPercent: number;
  progressSource: string;
  elapsedMs: number;
  etaSeconds: number;
  completedUnits: number;
  totalUnits: number;
  unit: string;
  throughputUnitsPerSecond: number;
  workerThreads: number;
  pixelsCompleted: number;
  pixelsTotal: number;
  inputBytes: number;
  attempt: number;
  maxRetries: number;
  priority: string;
  queuedUtc: string;
  resourceUsage: RuntimeTelemetry;
};

export type MachineQueueItem = MachineTaskActivity & {
  kind: string;
  status: string;
  priority: string;
  assignedPeerId: string;
  originNodeId: string;
  queuedUtc: string;
};

export type BayesianResourceScore = {
  dimension: string;
  mean: number;
  lowerBound: number;
  evidence: number;
  shortTermMean: number;
  longTermMean: number;
};

export type MachineActivity = {
  nodeId: string;
  identityId: string;
  online: boolean;
  selfNode: boolean;
  schedulerActive: boolean;
  status: string;
  roles: string[];
  appVersion: string;
  releaseChannel: string;
  releaseBuild: string;
  httpBaseUrl: string;
  meshPostUrl: string;
  relayCapable: boolean;
  features: string[];
  candidates: MachineCandidate[];
  transportAttestations: TransportAttestation[];
  platform: string;
  cpuCount: number;
  telemetry: RuntimeTelemetry;
  resourceReputation: BayesianResourceScore[];
  activeTasks: MachineTaskActivity[];
  taskQueue: MachineQueueItem[];
  lastSeenUnix: number;
  lastSeenUtc: string;
  lastClaimPollUtc: string;
  lastClaimError: string;
  lastResponseOk?: boolean | null;
  lastResponseItemId: string;
  lastResponseUtc: string;
};

export type NodeActivity = {
  knownResults: number;
  knownTasks: number;
  lastResult: string;
  storageBytes: number;
  history: HistoryItem[];
  machines: MachineActivity[];
};

export type NodeDiagnostics = {
  repoRoot: string;
  siliciumCli: string;
  logDir: string;
  nodePid?: number | null;
  supervisorPid?: number | null;
  nodeRunning: boolean;
  supervisorRunning: boolean;
  portReady: boolean;
  orchestrator: CheckItem;
  openssl: CheckItem;
  python: CheckItem;
  logTail: string;
};

export type AppDefaults = {
  repoRoot: string;
  advertiseHost: string;
  orchestratorUrl: string;
  nodeId: string;
};

export type MachineCandidate = {
  candidateType: string;
  transport: string;
  ip: string;
  port: number;
  internetRoutable: boolean;
  source: string;
};

export type TransportAttestation = {
  claimHash: string;
  signature: string;
  route: 'direct' | 'relay' | 'central' | 'failed' | string;
  transportBackend: string;
  proofScope: string;
  remotePeerId: string;
  sessionId: string;
  taskId: string;
  contentId: string;
  sizeBytes: number;
  endpoint: string;
  relayPeerId: string;
  peerProofVerified: boolean;
  success: boolean;
  failureReason: string;
  timestampUnix: number;
};

export type UpdateStatus = {
  currentVersion: string;
  currentChannel: string;
  currentBuild: string;
  latestVersion: string;
  latestBuild: string;
  latestContentId: string;
  state: 'unknown' | 'checking' | 'current' | 'available' | 'waiting_for_idle' | 'downloading' | 'installing' | 'error';
  updateAvailable: boolean;
  automatic: boolean;
  lastCheckedUtc: string;
  error: string;
  checkIntervalSeconds: number;
};

export async function startNode(config: NodeConfig): Promise<string> {
  return await invoke<string>('start_node', { config });
}

export async function stopNode(repoRoot?: string): Promise<string> {
  return await invoke<string>('stop_node', { repoRoot });
}

export async function nodeStatus(repoRoot?: string): Promise<NodeStatus> {
  return await invoke<NodeStatus>('node_status', { repoRoot });
}

export async function checkEnvironment(repoRoot: string): Promise<CheckItem[]> {
  return await invoke<CheckItem[]>('check_environment', { repoRoot });
}

export async function installRuntime(repoRoot: string): Promise<string> {
  return await invoke<string>('install_runtime', { repoRoot });
}

export async function nodeActivity(repoRoot: string): Promise<NodeActivity> {
  return await invoke<NodeActivity>('node_activity', { repoRoot });
}

export async function nodeDiagnostics(repoRoot: string): Promise<NodeDiagnostics> {
  return await invoke<NodeDiagnostics>('node_diagnostics', { repoRoot });
}

export async function appDefaults(): Promise<AppDefaults> {
  return await invoke<AppDefaults>('app_defaults');
}

export async function updateStatus(): Promise<UpdateStatus> {
  return await invoke<UpdateStatus>('update_status');
}

export async function checkForUpdates(): Promise<UpdateStatus> {
  return await invoke<UpdateStatus>('check_for_updates');
}
