<template>
  <div class="bg-[#1f2029] border border-white/5 rounded-2xl p-6 flex flex-col h-[500px] relative overflow-hidden group">
    <div class="flex items-center justify-between mb-4 z-10">
      <div>
        <h3 class="text-xl font-bold bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">
          Topologie du Reseau
        </h3>
        <p class="text-xs text-white/40">Visualisation en temps reel des noeuds P2P actifs</p>
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

          <!-- Links (Connections) -->
          <g v-for="(node, index) in visualNodes" :key="'link-' + node.id">
            <line
              v-if="node.id !== 'orchestrator-1'"
              :x1="center.x"
              :y1="center.y"
              :x2="node.x"
              :y2="node.y"
              stroke="url(#line-gradient)"
              stroke-width="1.5"
              stroke-opacity="0.4"
            />
            <!-- Animated pulse along the line -->
            <circle
              v-if="node.id !== 'orchestrator-1'"
              r="3"
              fill="#60a5fa"
            >
              <animateMotion
                :path="`M ${center.x} ${center.y} L ${node.x} ${node.y}`"
                dur="3s"
                repeatCount="indefinite"
              />
            </circle>
          </g>

          <!-- Glow under Orchestrator -->
          <circle :cx="center.x" :cy="center.y" r="50" fill="url(#glow)" />

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
              v-if="node.id !== 'orchestrator-1'"
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
            <span class="w-2.5 h-2.5 rounded-full bg-purple-500"></span> Orchestrateur
          </div>
          <div class="flex items-center gap-1">
            <span class="w-2.5 h-2.5 rounded-full bg-blue-500"></span> Worker Node
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
              <span
                v-if="selectedNode.outdated"
                class="mt-1 inline-flex rounded bg-amber-500/15 px-2 py-1 text-[9px] font-bold text-amber-300"
              >
                Mise a jour requise{{ selectedNode.latest_version ? ` vers ${selectedNode.latest_version}` : '' }}
              </span>
            </div>

            <div>
              <span class="text-white/40 block">Materiel :</span>
              <span class="text-white block mt-0.5">
                {{ selectedNode.capacity?.cpu_count || '?' }} Cores CPU
              </span>
            </div>

            <div>
              <span class="text-white/40 block">Candidats P2P/ICE :</span>
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
                  Aucun candidat (ICE bloque !)
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

type Peer = {
  node_id: string;
  roles: string[];
  http_base_url: string;
  last_seen_unix: number;
  candidates: Candidate[];
  app_version?: string;
  release_channel?: string;
  release_build?: string;
  latest_version?: string;
  version_status?: string;
  outdated?: boolean;
  capacity?: {
    platform?: string;
    cpu_count?: number;
  };
  self?: boolean;
};

const peers = ref<Peer[]>([]);
const selectedNode = ref<Peer | null>(null);
let intervalId: any = null;

const center = { x: 250, y: 180 };
const outdatedPeers = computed(() => peers.value.filter((peer) => peer.node_id !== 'orchestrator-1' && peer.outdated));

const visualNodes = computed(() => {
  if (peers.value.length === 0) return [];

  const nodes = [];
  const otherPeers = peers.value.filter((p) => p.node_id !== 'orchestrator-1');

  // Central Orchestrator Node
  const orchestrator = peers.value.find((p) => p.node_id === 'orchestrator-1');
  nodes.push({
    id: 'orchestrator-1',
    x: center.x,
    y: center.y,
    size: 20,
    color: '#a855f7', // Purple
    statusColor: '#10b981', // Green
    raw: orchestrator || { node_id: 'orchestrator-1', roles: ['orchestrator'], http_base_url: '', last_seen_unix: 0, candidates: [] },
  });

  // Calculate layout of peripheral nodes
  const radius = 120;
  otherPeers.forEach((peer, i) => {
    const angle = (i * 2 * Math.PI) / otherPeers.length;
    const x = center.x + radius * Math.cos(angle);
    const y = center.y + radius * Math.sin(angle);

    // Determine status color based on candidate state
    let statusColor = '#10b981'; // Green (Online & ready)
    if (peer.outdated) {
      statusColor = '#ef4444'; // Red (release obsolete/unknown)
    } else if (!peer.candidates || peer.candidates.length === 0) {
      statusColor = '#f59e0b'; // Yellow (Warning: NAT blocked/No candidates)
    }

    nodes.push({
      id: peer.node_id,
      x,
      y,
      size: 14,
      color: '#3b82f6', // Blue
      statusColor,
      raw: peer,
    });
  });

  return nodes;
});

const shortenId = (id: string) => {
  if (id.startsWith('silicium-')) {
    return id.substring(9);
  }
  return id;
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
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await $fetch<any>(`${props.apiBase}/jobs/network/peers`, { headers });
    if (res && res.peers) {
      peers.value = res.peers;

      // Keep selection updated
      if (selectedNode.value) {
        const updated = res.peers.find((p: Peer) => p.node_id === selectedNode.value?.node_id);
        if (updated) selectedNode.value = updated;
      } else if (res.peers.length > 0) {
        // Default select orchestrator
        const orch = res.peers.find((p: Peer) => p.node_id === 'orchestrator-1');
        if (orch) selectedNode.value = orch;
      }
    }
  } catch (error) {
    console.error('Failed to fetch peers visualizer data:', error);
  }
};

onMounted(() => {
  fetchPeers();
  intervalId = setInterval(fetchPeers, 5000);
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
