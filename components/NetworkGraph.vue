<template>
  <div class="bg-[#1f2029] border border-white/5 rounded-2xl p-6 flex flex-col min-h-[720px] relative overflow-hidden group">
    <div class="flex items-center justify-between mb-4 z-10">
      <div>
        <h3 class="text-xl font-bold bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">
          Topologie attestee du reseau
        </h3>
        <p class="text-xs text-white/40">Seuls les chemins observes et signes sont relies</p>
      </div>
      <div class="flex items-center space-x-2">
        <span class="w-2 h-2 rounded-full bg-green-500 animate-ping"></span>
        <span class="text-xs font-semibold text-green-400">{{ peers.length }} Connecte(s)</span>
      </div>
    </div>

    <div
      v-if="outdatedPeers.length > 0"
      class="mb-4 z-10 rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-100"
    >
      <strong class="block text-amber-300">{{ outdatedPeers.length }} node(s) a mettre a jour</strong>
      <span>Une version ancienne ou inconnue peut provoquer des echecs P2P, de calcul ou de verification.</span>
    </div>

    <div v-if="allActiveTasks.length" class="mb-4 z-10 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
      <article
        v-for="entry in allActiveTasks"
        :key="`${entry.peer.node_id}-${entry.task.item_id}`"
        class="relative overflow-hidden rounded-xl border border-cyan-400/20 bg-black/30 p-3 text-xs"
      >
        <span
          class="absolute inset-y-0 left-0 bg-gradient-to-r from-purple-600/30 to-cyan-400/20 transition-all duration-700"
          :style="{ width: `${clampProgress(entry.task.progress_percent)}%` }"
        ></span>
        <div class="relative z-10 space-y-1">
          <div class="flex items-center justify-between gap-3">
            <strong class="truncate text-white">{{ entry.task.workload || entry.task.activity || 'Tache reseau' }}</strong>
            <strong class="text-cyan-200">{{ progressLabel(entry.task.progress_percent) }}</strong>
          </div>
          <div class="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-white/55">
            <span>{{ entry.peer.node_id }}</span>
            <span>{{ roleLabel(entry.task.role) }}</span>
            <span>{{ phaseLabel(entry.task.phase) }}</span>
            <span>{{ sourceLabel(entry.task.progress_source) }}</span>
          </div>
          <div class="flex flex-wrap gap-x-3 text-[10px] text-white/70">
            <span>{{ formatDurationMs(entry.task.elapsed_ms) }} ecoule</span>
            <span>ETA {{ entry.task.eta_seconds ? formatDurationMs(entry.task.eta_seconds * 1000) : 'calcul...' }}</span>
            <span v-if="entry.task.throughput_units_per_second">{{ formatNumber(entry.task.throughput_units_per_second) }} {{ entry.task.unit }}/s</span>
          </div>
        </div>
      </article>
    </div>

    <!-- Main Visualizer Area -->
    <div class="flex-1 flex gap-6 min-h-0 z-10">
      <!-- SVG Network Canvas -->
      <div class="flex-1 bg-black/30 rounded-xl border border-white/5 relative overflow-hidden">
        <svg class="w-full h-full" viewBox="0 0 500 400">
          <!-- Definitions for gradients/glow effects -->
          <defs>
            <radialGradient id="glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stop-color="#a855f7" stop-opacity="0.4" />
              <stop offset="100%" stop-color="#a855f7" stop-opacity="0" />
            </radialGradient>
            <radialGradient id="node-glow-active" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.5" />
              <stop offset="100%" stop-color="#3b82f6" stop-opacity="0" />
            </radialGradient>
            <linearGradient id="line-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#a855f7" />
              <stop offset="100%" stop-color="#3b82f6" />
            </linearGradient>
          </defs>

          <!-- Signed transport paths only: candidates alone never create a link. -->
          <g v-for="link in visualLinks" :key="link.id">
            <line
              :x1="link.source.x"
              :y1="link.source.y"
              :x2="link.target.x"
              :y2="link.target.y"
              :stroke="link.color"
              :stroke-width="link.route === 'direct' ? 2.5 : 1.5"
              :stroke-dasharray="link.route === 'direct' ? undefined : '6 5'"
              stroke-opacity="0.7"
            />
            <circle
              r="3"
              :fill="link.color"
            >
              <animateMotion
                :path="`M ${link.source.x} ${link.source.y} L ${link.target.x} ${link.target.y}`"
                dur="3s"
                repeatCount="indefinite"
              />
            </circle>
          </g>

          <!-- Nodes Drawing -->
          <g
            v-for="node in visualNodes"
            :key="'node-' + node.id"
            class="cursor-pointer select-none"
            @click="selectNode(node.raw)"
          >
            <!-- Highlight Selection Ring -->
            <circle
              v-if="selectedNode && selectedNode.node_id === node.id"
              :cx="node.x"
              :cy="node.y"
              :r="node.size + 8"
              fill="none"
              stroke="#a855f7"
              stroke-width="2"
              class="animate-pulse"
            />

            <!-- Glow Effect for Node -->
            <circle
              :cx="node.x"
              :cy="node.y"
              :r="node.size + 12"
              fill="url(#node-glow-active)"
            />

            <!-- Main Circle -->
            <circle
              :cx="node.x"
              :cy="node.y"
              :r="node.size"
              :fill="node.color"
              class="transition-all duration-300 hover:scale-110"
              :stroke="selectedNode && selectedNode.node_id === node.id ? '#ffffff' : 'rgba(255,255,255,0.1)'"
              stroke-width="2"
            />

            <!-- Status Indicator Badge (mini dot on node) -->
            <circle
              :cx="node.x + node.size - 2"
              :cy="node.y - node.size + 2"
              r="4"
              :fill="node.statusColor"
              stroke="#131419"
              stroke-width="1.5"
            />

            <!-- Label -->
            <text
              :x="node.x"
              :y="node.y + node.size + 15"
              fill="#ffffff"
              font-size="10"
              font-weight="bold"
              text-anchor="middle"
              fill-opacity="0.8"
            >
              {{ shortenId(node.id) }}
            </text>
          </g>
        </svg>

        <!-- Legend overlay -->
        <div class="absolute bottom-2 left-2 bg-black/50 backdrop-blur-sm rounded-lg p-2 border border-white/5 flex gap-3 text-[10px] text-white/60">
          <div class="flex items-center gap-1">
            <span class="w-2.5 h-2.5 rounded-full bg-green-500"></span> Direct atteste
          </div>
          <div class="flex items-center gap-1">
            <span class="w-2.5 h-2.5 rounded-full bg-purple-500"></span> Relay atteste
          </div>
          <div class="flex items-center gap-1">
            <span class="w-2.5 h-2.5 rounded-full bg-rose-500"></span> Flux central observe
          </div>
        </div>
      </div>

      <!-- Sidebar: Selected Node Specs -->
      <div class="w-56 bg-black/20 rounded-xl border border-white/5 p-4 flex flex-col justify-between text-xs overflow-y-auto">
        <div v-if="selectedNode">
          <div class="border-b border-white/5 pb-2 mb-3">
            <div class="font-bold text-white text-sm truncate">{{ selectedNode.node_id }}</div>
            <div class="text-[10px] text-white/40 mt-0.5">
              Derniere vue : {{ formatTime(selectedNode.last_seen_unix) }}
            </div>
          </div>

          <div class="space-y-2">
            <div>
              <span class="text-white/40 block">Roles :</span>
              <div class="flex flex-wrap gap-1 mt-1">
                <span
                  v-for="role in selectedNode.roles"
                  :key="role"
                  class="px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 font-semibold text-[9px] uppercase"
                >
                  {{ role }}
                </span>
              </div>
            </div>

            <div>
              <span class="text-white/40 block">IP Observée :</span>
              <span class="text-white font-mono block mt-0.5 break-all">
                {{ selectedNode.http_base_url || 'N/A' }}
              </span>
            </div>

            <div>
              <span class="text-white/40 block">Plateforme :</span>
              <span class="text-white block mt-0.5 truncate" :title="selectedNode.capacity?.platform">
                {{ selectedNode.capacity?.platform || 'Unknown' }}
              </span>
            </div>

            <div>
              <span class="text-white/40 block">Version active :</span>
              <span class="text-white block mt-0.5">
                {{ selectedNode.app_version || 'inconnue' }} ({{ selectedNode.release_channel || 'canal inconnu' }})
              </span>
              <span class="text-[9px] text-white/40 font-mono">
                build {{ shortenHash(selectedNode.release_build || '') || 'inconnu' }}
              </span>
              <span
                v-if="selectedNode.outdated"
                class="mt-1 inline-flex rounded bg-amber-500/15 px-2 py-1 text-[9px] font-bold text-amber-300"
              >
                Mise a jour requise{{ selectedNode.latest_version ? ` vers ${selectedNode.latest_version}` : '' }}
              </span>
            </div>

            <div>
              <span class="text-white/40 block">Reputation bayesienne :</span>
              <div v-if="reputationRows(selectedNode).length" class="mt-1 space-y-1">
                <div
                  v-for="score in reputationRows(selectedNode)"
                  :key="score.dimension"
                  class="rounded bg-white/5 p-2"
                >
                  <div class="flex justify-between font-semibold text-cyan-200">
                    <span>{{ reputationLabel(score.dimension) }}</span>
                    <span>{{ percent(score.combined?.mean) }}</span>
                  </div>
                  <div class="my-1 h-1.5 overflow-hidden rounded-full bg-white/10">
                    <div
                      class="h-full rounded-full bg-gradient-to-r from-purple-500 via-cyan-400 to-green-400"
                      :style="{ width: percent(score.combined?.mean) }"
                    ></div>
                  </div>
                  <div class="text-[9px] text-white/40">
                    borne sure {{ percent(score.combined?.lower_bound) }} · {{ evidence(score.combined?.evidence) }} preuves
                  </div>
                  <div class="text-[9px] text-white/40">
                    court {{ percent(score.short_term?.mean) }} · long {{ percent(score.long_term?.mean) }}
                  </div>
                </div>
              </div>
              <span v-else class="text-yellow-400/80 text-[9px]">Aucune reputation bayesienne annoncee.</span>
            </div>

            <div>
              <span class="text-white/40 block">Materiel :</span>
              <span class="text-white block mt-0.5">
                {{ selectedNode.capacity?.cpu_count || '?' }} Cores CPU
              </span>
            </div>

            <div>
              <span class="text-white/40 block">Telemetrie temps reel :</span>
              <div class="mt-1 grid grid-cols-2 gap-1">
                <div class="rounded bg-white/5 p-2"><span class="block text-[9px] text-white/40">CPU machine</span><strong class="text-cyan-200">{{ metricPercent(selectedTelemetry.system_cpu_percent) }}</strong></div>
                <div class="rounded bg-white/5 p-2"><span class="block text-[9px] text-white/40">CPU Silicium</span><strong class="text-cyan-200">{{ metricPercent(selectedTelemetry.process_cpu_percent) }}</strong></div>
                <div class="rounded bg-white/5 p-2"><span class="block text-[9px] text-white/40">RAM machine</span><strong class="text-cyan-200">{{ metricPercent(selectedTelemetry.system_memory_percent) }}</strong></div>
                <div class="rounded bg-white/5 p-2"><span class="block text-[9px] text-white/40">RAM Silicium</span><strong class="text-cyan-200">{{ formatBytes(selectedTelemetry.process_rss_bytes) }}</strong></div>
                <div class="rounded bg-white/5 p-2"><span class="block text-[9px] text-white/40">Stockage</span><strong class="text-cyan-200">{{ metricPercent(selectedTelemetry.storage_used_percent) }}</strong></div>
                <div class="rounded bg-white/5 p-2"><span class="block text-[9px] text-white/40">Uptime</span><strong class="text-cyan-200">{{ formatDurationMs((selectedTelemetry.node_uptime_seconds || 0) * 1000) }}</strong></div>
              </div>
            </div>

            <div v-if="selectedNode.activity?.active_tasks?.length">
              <span class="text-white/40 block">Taches actives :</span>
              <article
                v-for="task in selectedNode.activity.active_tasks"
                :key="task.item_id"
                class="relative mt-1 overflow-hidden rounded-lg border border-cyan-400/20 bg-black/30 p-2"
              >
                <span class="absolute inset-y-0 left-0 bg-cyan-500/15" :style="{ width: `${clampProgress(task.progress_percent)}%` }"></span>
                <div class="relative z-10 space-y-1">
                  <div class="flex justify-between gap-2 font-semibold text-white"><span class="truncate">{{ roleLabel(task.role) }} / {{ task.workload }}</span><span>{{ progressLabel(task.progress_percent) }}</span></div>
                  <div class="text-[9px] text-white/50">{{ phaseLabel(task.phase) }} / {{ sourceLabel(task.progress_source) }} / {{ formatDurationMs(task.elapsed_ms) }}</div>
                  <div class="grid grid-cols-2 gap-1 text-[9px] text-white/70">
                    <span>ETA {{ task.eta_seconds ? formatDurationMs(task.eta_seconds * 1000) : '...' }}</span>
                    <span>{{ task.worker_threads || '?' }} threads</span>
                    <span v-if="task.pixels_total">{{ formatNumber(task.pixels_completed) }}/{{ formatNumber(task.pixels_total) }} px</span>
                    <span v-if="task.throughput_units_per_second">{{ formatNumber(task.throughput_units_per_second) }} {{ task.unit }}/s</span>
                    <span>CPU {{ metricPercent(task.resource_usage?.system_cpu_percent) }}</span>
                    <span>RAM {{ formatBytes(task.resource_usage?.process_rss_bytes) }}</span>
                  </div>
                </div>
              </article>
            </div>

            <div>
              <span class="text-white/40 block">Chemins de transport signes :</span>
              <div class="mt-1 space-y-1">
                <div
                  v-for="proof in selectedNode.transport_attestations || []"
                  :key="proof.claim_hash"
                  class="bg-white/5 p-2 rounded text-[9px] text-white/80"
                >
                  <div class="flex justify-between gap-2 font-bold" :class="proofColorClass(proof.route)">
                    <span>{{ proofLabel(proof) }}</span>
                    <span>{{ proof.proof_scope }}</span>
                  </div>
                  <div class="mt-1 break-all font-mono">{{ shortenHash(proof.claim_hash) }}</div>
                  <div class="mt-1 text-white/40">
                    {{ proof.peer_proof_verified ? 'preuve distante + observation locale signees' : 'observation locale signee' }}
                  </div>
                </div>
                <div v-if="!selectedNode.transport_attestations || selectedNode.transport_attestations.length === 0" class="text-yellow-400/80 font-bold">
                  Aucun chemin signe : le P2P n est pas atteste.
                </div>
              </div>
            </div>

            <div>
              <span class="text-white/40 block">Candidats P2P/ICE (possibilites) :</span>
              <div class="mt-1 space-y-1">
                <div
                  v-for="cand in selectedNode.candidates"
                  :key="cand.candidate_id"
                  class="bg-white/5 p-1 rounded font-mono text-[9px] text-white/80"
                >
                  <div class="flex justify-between font-bold text-blue-300">
                    <span>{{ cand.candidate_type }}</span>
                    <span>{{ cand.transport }}</span>
                  </div>
                  <div class="truncate mt-0.5">{{ cand.ip }}:{{ cand.port }}</div>
                </div>
                <div v-if="!selectedNode.candidates || selectedNode.candidates.length === 0" class="text-yellow-400/80 font-bold">
                  Aucun candidat ICE annonce.
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="h-full flex items-center justify-center text-center text-white/30 px-2">
          Cliquez sur un noeud pour voir ses specifications.
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import Cookies from 'js-cookie';

const props = defineProps({
  apiBase: {
    type: String,
    required: true,
  },
});

type Candidate = {
  candidate_id: string;
  candidate_type: string;
  transport: string;
  ip: string;
  port: number;
};

type TransportAttestation = {
  claim_hash: string;
  route: 'direct' | 'relay' | 'central' | 'failed' | string;
  transport_backend: string;
  proof_scope: string;
  remote_peer_id: string;
  relay_peer_id?: string;
  peer_proof_verified: boolean;
  success: boolean;
  timestamp_unix: number;
};

type RuntimeTelemetry = {
  system_cpu_percent?: number;
  process_cpu_percent?: number;
  process_cpu_percent_one_core?: number;
  process_rss_bytes?: number;
  process_peak_rss_bytes?: number;
  system_memory_used_bytes?: number;
  system_memory_total_bytes?: number;
  system_memory_percent?: number;
  storage_used_percent?: number;
  storage_free_bytes?: number;
  node_uptime_seconds?: number;
  logical_cpu_count?: number;
  python_thread_count?: number;
};

type ActiveTask = {
  item_id: string;
  role?: string;
  activity?: string;
  workload?: string;
  phase?: string;
  progress_percent?: number;
  progress_source?: string;
  elapsed_ms?: number;
  eta_seconds?: number;
  completed_units?: number;
  total_units?: number;
  unit?: string;
  throughput_units_per_second?: number;
  worker_threads?: number;
  pixels_completed?: number;
  pixels_total?: number;
  attempt?: number;
  max_retries?: number;
  resource_usage?: RuntimeTelemetry;
};

type Peer = {
  node_id: string;
  roles: string[];
  http_base_url: string;
  last_seen_unix: number;
  candidates: Candidate[];
  transport_attestations?: TransportAttestation[];
  app_version?: string;
  release_channel?: string;
  release_build?: string;
  latest_version?: string;
  version_status?: string;
  outdated?: boolean;
  resource_reputation?: {
    schema?: string;
    dimensions?: Record<string, BayesianDimension>;
  };
  capacity?: {
    platform?: string;
    cpu_count?: number;
  };
  telemetry?: RuntimeTelemetry;
  activity?: {
    status?: string;
    telemetry?: RuntimeTelemetry;
    active_tasks?: ActiveTask[];
  };
  self?: boolean;
};

type BayesianSummary = {
  mean?: number;
  lower_bound?: number;
  upper_bound?: number;
  evidence?: number;
};

type BayesianDimension = {
  short_term?: BayesianSummary;
  long_term?: BayesianSummary;
  combined?: BayesianSummary;
};

const peers = ref<Peer[]>([]);
const selectedNode = ref<Peer | null>(null);
let intervalId: any = null;

const center = { x: 250, y: 180 };
const outdatedPeers = computed(() => peers.value.filter((peer) => peer.node_id !== 'orchestrator-1' && peer.outdated));
const allActiveTasks = computed(() => peers.value.flatMap((peer) => (
  (peer.activity?.active_tasks || []).map((task) => ({ peer, task }))
)));
const selectedTelemetry = computed<RuntimeTelemetry>(() => (
  selectedNode.value?.activity?.telemetry || selectedNode.value?.telemetry || {}
));

const visualNodes = computed(() => {
  if (peers.value.length === 0) return [];

  const nodes: Array<{
    id: string;
    x: number;
    y: number;
    size: number;
    color: string;
    statusColor: string;
    raw: Peer;
  }> = [];
  const radius = peers.value.length === 1 ? 0 : 125;
  peers.value.forEach((peer, i) => {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / peers.value.length;
    const x = center.x + radius * Math.cos(angle);
    const y = center.y + radius * Math.sin(angle);

    const latestProof = peer.transport_attestations?.[0];
    let statusColor = '#f59e0b';
    if (peer.outdated) {
      statusColor = '#ef4444';
    } else if (latestProof?.route === 'direct' && latestProof.success) {
      statusColor = '#10b981';
    } else if (latestProof?.route === 'relay') {
      statusColor = '#a855f7';
    } else if (latestProof?.route === 'central') {
      statusColor = '#f43f5e';
    }

    nodes.push({
      id: peer.node_id,
      x,
      y,
      size: peer.node_id === 'orchestrator-1' ? 17 : 14,
      color: peer.node_id === 'orchestrator-1' ? '#a855f7' : '#3b82f6',
      statusColor,
      raw: peer,
    });
  });

  return nodes;
});

const visualLinks = computed(() => {
  const nodes = new Map(visualNodes.value.map((node) => [node.id, node]));
  const links: Array<{
    id: string;
    route: string;
    color: string;
    source: (typeof visualNodes.value)[number];
    target: (typeof visualNodes.value)[number];
  }> = [];
  const seen = new Set<string>();
  for (const peer of peers.value) {
    const source = nodes.get(peer.node_id);
    if (!source) continue;
    for (const proof of peer.transport_attestations || []) {
      if (!proof.success || !['direct', 'relay', 'central'].includes(proof.route)) continue;
      const targetId = proof.route === 'relay' && proof.relay_peer_id
        ? proof.relay_peer_id
        : proof.remote_peer_id;
      const target = nodes.get(targetId);
      if (!target || target.id === source.id) continue;
      const pair = [source.id, target.id].sort().join(':');
      const id = `${pair}:${proof.route}`;
      if (seen.has(id)) continue;
      seen.add(id);
      links.push({
        id,
        route: proof.route,
        color: proof.route === 'direct' ? '#22c55e' : proof.route === 'relay' ? '#a855f7' : '#f43f5e',
        source,
        target,
      });
    }
  }
  return links;
});

const shortenId = (id: string) => {
  if (id.startsWith('silicium-')) {
    return id.substring(9);
  }
  return id;
};

const shortenHash = (hash: string) => hash.length > 24 ? `${hash.slice(0, 12)}...${hash.slice(-8)}` : hash;
const reputationRows = (peer: Peer) => {
  const dimensions = peer.resource_reputation?.dimensions || {};
  return ['connection', 'storage', 'compute', 'verify', 'delegation']
    .filter((dimension) => dimensions[dimension])
    .map((dimension) => ({ dimension, ...dimensions[dimension] }));
};
const reputationLabel = (dimension: string) => ({
  connection: 'Connexion',
  storage: 'Stockage',
  compute: 'Calcul',
  verify: 'Verification',
  delegation: 'Delegation',
}[dimension] || dimension);
const percent = (value?: number) => `${Math.round(Math.max(0, Math.min(1, value || 0)) * 100)}%`;
const evidence = (value?: number) => (value || 0) >= 100 ? Math.round(value || 0) : (value || 0).toFixed(1);
const clampProgress = (value?: number) => Math.max(0, Math.min(100, Number(value) || 0));
const progressLabel = (value?: number) => `${clampProgress(value).toFixed(value && value < 10 ? 1 : 0)}%`;
const metricPercent = (value?: number) => `${Math.max(0, Number(value) || 0).toFixed(1)}%`;
const formatNumber = (value?: number) => new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 }).format(Number(value) || 0);
const formatBytes = (value?: number) => {
  let amount = Math.max(0, Number(value) || 0);
  const units = ['o', 'Ko', 'Mo', 'Go', 'To'];
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
};
const formatDurationMs = (value?: number) => {
  const seconds = Math.max(0, Math.round((Number(value) || 0) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
};
const roleLabel = (role?: string) => role === 'verify' ? 'Verification' : role === 'compute' ? 'Calcul' : role || 'Tache';
const phaseLabel = (phase?: string) => ({
  fetching_input: 'Recuperation',
  executing: 'Execution',
  rendering: 'Rendu',
  publishing_result: 'Publication',
  finalizing: 'Finalisation',
}[phase || ''] || phase || 'Execution');
const sourceLabel = (source?: string) => source === 'measured' ? 'mesuree' : source === 'estimated' ? 'estimee' : 'indisponible';

const proofLabel = (proof: TransportAttestation) => {
  if (proof.route === 'direct' && proof.transport_backend === 'ice') return 'Direct ICE prouve';
  if (proof.route === 'direct') return 'Direct pair observe';
  if (proof.route === 'relay') return 'Relay observe';
  if (proof.route === 'central') return 'Flux central observe';
  return 'Connexion echouee';
};

const proofColorClass = (route: string) => {
  if (route === 'direct') return 'text-green-300';
  if (route === 'relay') return 'text-purple-300';
  if (route === 'central') return 'text-rose-300';
  return 'text-yellow-300';
};

const formatTime = (unix: number) => {
  if (!unix) return 'N/A';
  const date = new Date(unix * 1000);
  return date.toLocaleTimeString();
};

const selectNode = (node: Peer) => {
  selectedNode.value = node;
};

const fetchPeers = async () => {
  try {
    const token = Cookies.get('auth_token');
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await $fetch<any>(`${props.apiBase}/jobs/network/peers`, { headers });
    if (res && res.peers) {
      peers.value = res.peers;

      // Keep selection updated
      if (selectedNode.value) {
        const updated = res.peers.find((p: Peer) => p.node_id === selectedNode.value?.node_id);
        if (updated) selectedNode.value = updated;
      } else if (res.peers.length > 0) {
        const orch = res.peers.find((p: Peer) => p.node_id === 'orchestrator-1');
        selectedNode.value = orch || res.peers[0];
      }
    }
  } catch (error) {
    console.error('Failed to fetch peers visualizer data:', error);
  }
};

onMounted(() => {
  fetchPeers();
  intervalId = setInterval(fetchPeers, 2000);
});

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId);
});
</script>

<style scoped>
/* Glowing lines and pulsing animations */
.animate-pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
@keyframes pulse {
  0%, 100% {
    opacity: 1;
    r: 22px;
  }
  50% {
    opacity: .3;
    r: 26px;
  }
}
</style>
