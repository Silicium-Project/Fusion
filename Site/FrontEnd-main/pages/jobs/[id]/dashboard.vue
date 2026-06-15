<template>
  <div class="min-h-screen bg-[#131419] text-white">
    <main class="max-w-7xl mx-auto px-6 py-8">
      <div class="flex flex-wrap items-center justify-between gap-4 mb-8">
        <div>
          <NuxtLink to="/dashboard" class="text-white/50 hover:text-white">Retour aux taches</NuxtLink>
          <h1 class="text-4xl font-bold mt-3">Dashboard</h1>
          <p class="text-white/50 mt-2">{{ payload?.job.title || 'Job Silicium' }}</p>
        </div>
        <div class="flex gap-3">
          <button @click="loadDashboard" class="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/15">
            Rafraichir
          </button>
          <button v-if="payload?.resultReady" @click="downloadResult" class="px-4 py-2 rounded-lg bg-green-500/20 text-green-200 hover:bg-green-500/30">
            Telecharger le rendu
          </button>
        </div>
      </div>

      <div v-if="errorMessage" class="mb-6 rounded-xl border border-red-400/30 bg-red-500/10 p-4 text-red-200">
        {{ errorMessage }}
      </div>

      <div v-if="payload" class="grid grid-cols-1 lg:grid-cols-4 gap-5 mb-6">
        <div class="bg-[#1f2029] rounded-2xl p-5">
          <p class="text-white/50">Statut</p>
          <p class="text-2xl font-bold mt-2">{{ payload.job.status }}</p>
        </div>
        <div class="bg-[#1f2029] rounded-2xl p-5">
          <p class="text-white/50">Fragments resolus</p>
          <p class="text-2xl font-bold mt-2">{{ verifiedFragments }} / {{ expectedFragmentCount }}</p>
        </div>
        <div class="bg-[#1f2029] rounded-2xl p-5">
          <p class="text-white/50">Devnet</p>
          <p class="text-2xl font-bold mt-2">{{ payload.devnet.ok ? 'trace ok' : 'non confirme' }}</p>
        </div>
        <div class="bg-[#1f2029] rounded-2xl p-5">
          <p class="text-white/50">Hash final</p>
          <p class="font-mono text-sm mt-2 break-all">{{ shortHash(finalHash) }}</p>
        </div>
      </div>

      <section v-if="payload" class="mb-6 bg-[#1f2029] rounded-2xl p-6">
        <div class="flex flex-wrap items-center justify-between gap-4 mb-5">
          <div>
            <h2 class="text-2xl font-bold">Puzzle du rendu</h2>
            <p class="text-white/50">Les fragments se remplissent pendant le calcul, puis passent en vert apres verification.</p>
          </div>
          <div class="text-right">
            <p class="text-white/50 text-sm">Etape courante</p>
            <p class="font-semibold">{{ payload.summary.stage || payload.job.status }}</p>
          </div>
        </div>
        <div class="h-3 rounded-full bg-black/30 overflow-hidden mb-5">
          <div class="h-full bg-gradient-to-r from-purple-400 to-green-400 transition-all" :style="{ width: `${progressPercent}%` }"></div>
        </div>
        <div class="grid gap-2" :style="{ gridTemplateColumns: `repeat(${puzzleColumns}, minmax(0, 1fr))` }">
          <div
            v-for="tile in puzzleTiles"
            :key="tile.id"
            class="min-h-16 rounded-lg border p-3 transition-colors"
            :class="tileClass(tile.status)"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="font-bold">#{{ tile.index }}</span>
              <span class="text-xs">{{ tile.status }}</span>
            </div>
            <p class="text-xs mt-2 opacity-70">y {{ tile.yStart }} -> {{ tile.yEnd }}</p>
          </div>
        </div>
      </section>

      <div v-if="payload" class="grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-6">
        <section class="bg-[#1f2029] rounded-2xl p-6">
          <div class="flex items-center justify-between gap-4 mb-4">
            <div>
              <h2 class="text-2xl font-bold">Graphe du job</h2>
              <p class="text-white/50">Split recursif, calcul des feuilles, verification puis reassemblage.</p>
            </div>
            <span class="text-white/50">{{ treeNodes.length }} noeuds</span>
          </div>
          <div class="relative overflow-auto rounded-xl bg-[#f8fafc] min-h-[520px]">
            <svg :width="graphSize.width" :height="graphSize.height" class="block">
              <defs>
                <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
                </marker>
              </defs>
              <line
                v-for="edge in treeEdges"
                :key="edge.id"
                :x1="edge.x1"
                :y1="edge.y1"
                :x2="edge.x2"
                :y2="edge.y2"
                stroke="#94a3b8"
                stroke-width="2"
                stroke-dasharray="5 5"
                marker-end="url(#arrow)"
              />
              <g v-for="node in treeNodes" :key="node.id" :transform="`translate(${node.x}, ${node.y})`">
                <rect :class="node.leaf ? 'fill-green-50 stroke-green-500' : 'fill-purple-50 stroke-purple-500'" width="170" height="74" rx="12" stroke-width="2" />
                <text x="14" y="24" fill="#0f172a" font-size="14" font-weight="700">Fragment {{ node.index }}</text>
                <text x="14" y="45" fill="#475569" font-size="12">{{ node.leaf ? 'verified leaf' : 'split parent' }}</text>
                <text x="14" y="62" fill="#64748b" font-size="11">depth {{ node.depth }} - {{ node.complexity }}</text>
              </g>
            </svg>
          </div>
        </section>

        <aside class="space-y-6">
          <section class="bg-[#1f2029] rounded-2xl p-6">
            <h2 class="text-2xl font-bold mb-4">Rendu final</h2>
            <div v-if="resultPreviewUrl" class="rounded-xl overflow-hidden bg-black/30 border border-white/10">
              <img :src="resultPreviewUrl" alt="Rendu final" class="w-full object-contain" />
            </div>
            <p v-else class="text-white/50">Le rendu sera disponible quand le job sera complete.</p>
          </section>

          <section class="bg-[#1f2029] rounded-2xl p-6">
            <h2 class="text-2xl font-bold mb-4">Trace Devnet</h2>
            <div class="space-y-3 text-sm">
              <div>
                <p class="text-white/50">Job</p>
                <p class="font-mono break-all">{{ payload.devnet.job || payload.job.devnetJob || 'non disponible' }}</p>
              </div>
              <div>
                <p class="text-white/50">Program</p>
                <p class="font-mono break-all">{{ payload.devnet.programId || 'non disponible' }}</p>
              </div>
              <div>
                <p class="text-white/50">Finalize tx</p>
                <p class="font-mono break-all">{{ payload.devnet.signatures?.finalize_job || 'non disponible' }}</p>
              </div>
            </div>
          </section>
        </aside>
      </div>

      <section v-if="payload" class="mt-6 bg-[#1f2029] rounded-2xl p-6">
        <div class="flex items-center justify-between gap-4 mb-4">
          <h2 class="text-2xl font-bold">Fragments resolus</h2>
          <span class="text-white/50">{{ fragments.length }}</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left">
            <thead class="text-white/50 text-sm">
              <tr>
                <th class="py-3">Fragment</th>
                <th class="py-3">Parent</th>
                <th class="py-3">Worker</th>
                <th class="py-3">Verification</th>
                <th class="py-3">Hash resultat</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="fragment in fragments" :key="fragment.fragment_id || fragment.fragment_index" class="border-t border-white/10">
                <td class="py-4 font-mono">#{{ fragment.fragment_index }}</td>
                <td class="py-4 text-white/70">{{ fragment.parent_index ?? 'racine' }}</td>
                <td class="py-4 text-white/70">{{ fragment.worker_output_ref?.shared_ref?.peer_id || fragment.worker_output_ref?.peer_id || 'worker' }}</td>
                <td class="py-4">
                  <span :class="fragment.verify_choice ? 'bg-green-500/20 text-green-200' : 'bg-yellow-500/20 text-yellow-200'" class="px-3 py-1 rounded-full text-sm">
                    {{ fragment.status || (fragment.verify_choice ? 'verified' : 'pending') }}
                  </span>
                </td>
                <td class="py-4 font-mono text-sm break-all">{{ shortHash(fragment.compute_result_hash || fragment.expected_hash) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import Cookies from 'js-cookie';

type DashboardPayload = {
  job: {
    id: number;
    title: string;
    status: string;
    siliciumJobId: string;
    devnetJob?: string;
  };
  resultReady: boolean;
  resultUrl: string;
  summary: Record<string, any>;
  devnet: Record<string, any>;
};

type TreeNode = {
  id: string;
  index: number;
  depth: number;
  complexity: number;
  leaf: boolean;
  x: number;
  y: number;
};

type TreeEdge = {
  id: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

const route = useRoute();
const config = useRuntimeConfig();
const apiBase = config.public.apiBase;
const payload = ref<DashboardPayload | null>(null);
const errorMessage = ref('');
const resultPreviewUrl = ref('');
const refreshTimer = ref<ReturnType<typeof setInterval> | null>(null);

const authHeaders = () => {
  const token = Cookies.get('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const fragments = computed<any[]>(() => Array.isArray(payload.value?.summary.fragments) ? payload.value?.summary.fragments : []);
const finalHash = computed(() => payload.value?.summary.finalHash || payload.value?.summary.reassembledHash || payload.value?.summary.expectedFullHash || '');
const splitTree = computed(() => payload.value?.summary.splitTree || payload.value?.devnet.splitTree || null);
const expectedFragmentCount = computed(() => Number(payload.value?.summary.fragmentCount || fragments.value.length || 0));
const verifiedFragments = computed(() => fragments.value.filter((fragment) => fragment.verify_choice || ['verified', 'reassembled'].includes(String(fragment.status))).length);
const progressPercent = computed(() => {
  const total = Math.max(1, expectedFragmentCount.value);
  const weighted = fragments.value.reduce((sum, fragment) => {
    const status = String(fragment.status || '');
    if (status === 'reassembled') return sum + 1;
    if (status === 'verified') return sum + 0.9;
    if (status === 'queued_verify') return sum + 0.65;
    if (status === 'computed') return sum + 0.55;
    if (status === 'queued_compute') return sum + 0.3;
    if (status === 'preparing') return sum + 0.15;
    return sum;
  }, 0);
  return Math.max(0, Math.min(100, Math.round((weighted / total) * 100)));
});
const puzzleColumns = computed(() => Math.max(1, Math.min(4, expectedFragmentCount.value || 1)));
const puzzleTiles = computed(() => {
  const sorted = [...fragments.value].sort((a, b) => Number(a.y_start ?? 0) - Number(b.y_start ?? 0));
  return sorted.map((fragment, index) => ({
    id: String(fragment.fragment_id || fragment.fragment_index || index),
    index: Number(fragment.fragment_index ?? index),
    yStart: Number(fragment.y_start ?? 0),
    yEnd: Number(fragment.y_end ?? 0),
    status: String(fragment.status || (fragment.verify_choice ? 'verified' : 'planned')),
  }));
});

const layoutTree = () => {
  const nodes: TreeNode[] = [];
  const edges: TreeEdge[] = [];
  const leaves: TreeNode[] = [];
  let nextLeaf = 0;
  const horizontalGap = 235;
  const verticalGap = 105;

  const walk = (raw: any, depth: number, parent?: TreeNode): TreeNode => {
    const children = Array.isArray(raw?.children) ? raw.children : [];
    const node: TreeNode = {
      id: `fragment-${raw?.fragment_index ?? nodes.length}`,
      index: Number(raw?.fragment_index ?? nodes.length),
      depth,
      complexity: Number(raw?.complexity_score ?? 0),
      leaf: children.length === 0 || Boolean(raw?.is_leaf),
      x: 40 + depth * horizontalGap,
      y: 40,
    };
    nodes.push(node);
    if (children.length === 0) {
      node.y = 40 + nextLeaf * verticalGap;
      nextLeaf += 1;
      leaves.push(node);
    } else {
      const childNodes = children.map((child: any) => walk(child, depth + 1, node));
      node.y = childNodes.reduce((sum: number, child: TreeNode) => sum + child.y, 0) / childNodes.length;
    }
    if (parent) {
      edges.push({
        id: `${parent.id}-${node.id}`,
        x1: parent.x + 170,
        y1: parent.y + 37,
        x2: node.x,
        y2: node.y + 37,
      });
    }
    return node;
  };

  if (splitTree.value) {
    walk(splitTree.value, 0);
  } else {
    fragments.value.forEach((fragment, index) => {
      nodes.push({
        id: `fragment-${fragment.fragment_index ?? index}`,
        index: Number(fragment.fragment_index ?? index),
        depth: Number(fragment.depth ?? 0),
        complexity: Number(fragment.complexity_score ?? 0),
        leaf: true,
        x: 40 + Number(fragment.depth ?? 0) * horizontalGap,
        y: 40 + index * verticalGap,
      });
    });
  }
  return { nodes, edges, leaves };
};

const treeNodes = computed(() => layoutTree().nodes);
const treeEdges = computed(() => layoutTree().edges);
const graphSize = computed(() => {
  const maxX = Math.max(720, ...treeNodes.value.map((node) => node.x + 220));
  const maxY = Math.max(520, ...treeNodes.value.map((node) => node.y + 120));
  return { width: maxX, height: maxY };
});

const loadResultPreview = async () => {
  if (!payload.value?.resultReady) return;
  if (resultPreviewUrl.value) return;
  if (resultPreviewUrl.value) URL.revokeObjectURL(resultPreviewUrl.value);
  const response = await fetch(`${apiBase}${payload.value.resultUrl}`, { headers: authHeaders() });
  if (!response.ok) return;
  const blob = await response.blob();
  resultPreviewUrl.value = URL.createObjectURL(blob);
};

const loadDashboard = async () => {
  errorMessage.value = '';
  try {
    payload.value = await $fetch<DashboardPayload>(`${apiBase}/jobs/${route.params.id}/dashboard`, {
      headers: authHeaders(),
    });
    await loadResultPreview();
    updateRefreshTimer();
  } catch (error: any) {
    errorMessage.value = error?.data || error?.message || 'Impossible de charger le dashboard du job.';
  }
};

const updateRefreshTimer = () => {
  const status = payload.value?.job.status || '';
  const shouldRefresh = ['queued', 'running'].includes(status);
  if (shouldRefresh && !refreshTimer.value) {
    refreshTimer.value = setInterval(loadDashboard, 2000);
  }
  if (!shouldRefresh && refreshTimer.value) {
    clearInterval(refreshTimer.value);
    refreshTimer.value = null;
  }
};

const downloadResult = async () => {
  if (!payload.value?.resultReady) return;
  const response = await fetch(`${apiBase}${payload.value.resultUrl}`, { headers: authHeaders() });
  if (!response.ok) return;
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${payload.value.job.siliciumJobId}-result.png`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
};

const shortHash = (value: any) => {
  const text = String(value || '');
  if (text.length <= 18) return text || 'non disponible';
  return `${text.slice(0, 10)}...${text.slice(-8)}`;
};

const tileClass = (status: string) => {
  if (status === 'reassembled' || status === 'verified') return 'border-green-400/50 bg-green-500/20 text-green-100';
  if (status === 'queued_verify') return 'border-blue-400/50 bg-blue-500/20 text-blue-100';
  if (status === 'computed') return 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100';
  if (status === 'queued_compute' || status === 'preparing') return 'border-purple-400/50 bg-purple-500/20 text-purple-100';
  if (status === 'verify_failed') return 'border-red-400/50 bg-red-500/20 text-red-100';
  return 'border-white/10 bg-black/20 text-white/60';
};

onMounted(loadDashboard);
onBeforeUnmount(() => {
  if (refreshTimer.value) clearInterval(refreshTimer.value);
  if (resultPreviewUrl.value) URL.revokeObjectURL(resultPreviewUrl.value);
});
</script>
