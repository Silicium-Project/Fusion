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

export type MachineTaskActivity = {
  itemId: string;
  role: string;
  activity: string;
  workload: string;
  fragmentIndex: string;
};

export type MachineActivity = {
  nodeId: string;
  online: boolean;
  schedulerActive: boolean;
  status: string;
  roles: string[];
  activeTasks: MachineTaskActivity[];
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
