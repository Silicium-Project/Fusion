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
};

export type NodeActivity = {
  knownResults: number;
  knownTasks: number;
  lastResult: string;
  storageBytes: number;
  history: HistoryItem[];
};

export async function startNode(config: NodeConfig): Promise<string> {
  return await invoke<string>('start_node', { config });
}

export async function stopNode(): Promise<string> {
  return await invoke<string>('stop_node');
}

export async function nodeStatus(): Promise<NodeStatus> {
  return await invoke<NodeStatus>('node_status');
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
