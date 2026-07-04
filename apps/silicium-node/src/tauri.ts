import { invoke } from '@tauri-apps/api/core';

export type NodeRole = 'worker' | 'verifier';

export type NodeConfig = {
  role: NodeRole;
  repoRoot: string;
  orchestratorUrl: string;
  advertiseHost: string;
  nodeId: string;
  reputationScore: number;
};

export type NodeStatus = {
  worker: boolean;
  verifier: boolean;
};

export async function startNode(config: NodeConfig): Promise<string> {
  return await invoke<string>('start_node', { config });
}

export async function stopNode(role: NodeRole): Promise<string> {
  return await invoke<string>('stop_node', { role });
}

export async function nodeStatus(): Promise<NodeStatus> {
  return await invoke<NodeStatus>('node_status');
}
