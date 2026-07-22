<template>
  <div class="min-h-screen bg-[#131419] text-white">
    <main class="max-w-7xl mx-auto px-6 py-8">
      <div class="flex flex-wrap items-center justify-between gap-4 mb-8">
        <div>
          <div class="flex flex-wrap gap-3">
            <NuxtLink to="/dashboard" class="px-4 py-2 rounded-lg bg-white/10 text-white/80 hover:bg-white/15 hover:text-white">
              Retour au tableau de bord
            </NuxtLink>
            <NuxtLink to="/" class="px-4 py-2 rounded-lg bg-black/20 text-white/60 hover:bg-white/10 hover:text-white">
              Accueil
            </NuxtLink>
          </div>
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

      <section v-if="payload?.job.errorMessage" class="mb-6 rounded-xl border border-red-400/30 bg-red-500/10 p-5">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 class="text-xl font-bold text-red-100">Erreur du job</h2>
            <p class="text-red-200/80 mt-1">
              Le pipeline a echoue pendant l'execution reseau. Le detail ci-dessous vient du backend.
            </p>
          </div>
          <span class="px-3 py-1 rounded-full bg-red-500/20 text-red-100 text-sm">{{ payload.job.workload }}</span>
        </div>
        <pre class="mt-4 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-4 text-sm text-red-100">{{ payload.job.errorMessage }}</pre>
      </section>

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
            <div class="flex items-center gap-3">
              <h2 class="text-2xl font-bold">Rendu distribue en direct</h2>
              <span v-if="payload.job.status === 'running'" class="live-badge"><i></i> LIVE</span>
            </div>
            <p class="text-white/50">Chaque bande apparait des que son worker renvoie les pixels, avant meme la reassemblage final.</p>
          </div>
          <div class="text-right">
            <p class="text-white/50 text-sm">Etape courante</p>
            <p class="font-semibold">{{ payload.summary.stage || payload.job.status }}</p>
          </div>
        </div>
        <div class="h-3 rounded-full bg-black/30 overflow-hidden mb-5">
          <div class="h-full bg-gradient-to-r from-purple-400 to-green-400 transition-all" :style="{ width: `${progressPercent}%` }"></div>
        </div>

        <div class="live-render-layout">
          <div class="live-render-stage">
            <div class="live-render-canvas" :style="{ aspectRatio: `${imageWidth} / ${imageHeight}` }">
              <div
                v-for="tile in puzzleTiles"
                :key="tile.id"
                class="live-render-tile"
                :class="tileVisualClass(tile)"
                :style="tilePosition(tile)"
              >
                <img
                  v-if="fragmentPreviewUrls[tile.index]"
                  :src="fragmentPreviewUrls[tile.index]"
                  :alt="`Fragment ${tile.index}`"
                  draggable="false"
                />
                <div v-else class="tile-placeholder">
                  <span class="tile-grid"></span>
                  <strong>#{{ tile.index }}</strong>
                  <small>{{ tileStatusLabel(tile.status) }}</small>
                </div>
                <div class="tile-state">
                  <span>#{{ tile.index }}</span>
                  <span>{{ tileStatusLabel(tile.status) }}</span>
                </div>
                <span v-if="tile.status === 'verified' || tile.status === 'reassembled'" class="verified-sweep"></span>
              </div>
              <div class="render-scanline" :class="{ active: payload.job.status === 'running' }"></div>
              <div class="render-vignette"></div>
              <div v-if="puzzleTiles.length === 0" class="render-empty">Preparation du decoupage...</div>
            </div>
          </div>

          <div class="live-render-legend">
            <div>
              <strong>{{ previewFragmentCount }}</strong>
              <span>tuiles visibles</span>
            </div>
            <div>
              <strong>{{ verifiedFragments }}</strong>
              <span>verifiees</span>
            </div>
            <div>
              <strong>{{ expectedFragmentCount }}</strong>
              <span>total</span>
            </div>
          </div>
        </div>

        <div class="mt-4 grid gap-2" :style="{ gridTemplateColumns: `repeat(${statusGridColumns}, minmax(0, 1fr))` }">
          <div
            v-for="tile in puzzleTiles"
            :key="`${tile.id}-status`"
            class="rounded-lg border px-3 py-2 transition-colors"
            :class="tileStatusClass(tile.status)"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="font-bold">#{{ tile.index }}</span>
              <span class="text-xs">{{ tileStatusLabel(tile.status) }}</span>
            </div>
            <p class="text-xs mt-1 opacity-70">x {{ tile.xStart }} → {{ tile.xEnd }} · y {{ tile.yStart }} → {{ tile.yEnd }}</p>
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

          <section class="bg-[#1f2029] rounded-2xl p-6">
            <h2 class="text-2xl font-bold mb-4">Diagnostics</h2>
            <div class="space-y-3 text-sm">
              <div>
                <p class="text-white/50">Workload</p>
                <p class="font-mono">{{ payload.job.workload }}</p>
              </div>
              <div>
                <p class="text-white/50">Etape</p>
                <p class="font-mono">{{ payload.summary.stage || payload.job.status }}</p>
              </div>
              <div>
                <p class="text-white/50">Dernier node run</p>
                <pre class="mt-1 max-h-44 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-3 text-xs">{{ latestNodeRunText }}</pre>
              </div>
              <div>
                <p class="text-white/50">Fichiers</p>
                <pre class="mt-1 max-h-36 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-3 text-xs">{{ diagnosticsText }}</pre>
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
                <th class="py-3">Echantillon audite</th>
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
                <td class="py-4 text-sm text-white/70">{{ verificationSummary(fragment) }}</td>
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
    description?: string;
    workload: string;
    priority?: string;
    status: string;
    siliciumJobId: string;
    devnetJob?: string;
    errorMessage?: string;
  };
  resultReady: boolean;
  resultUrl: string;
  diagnostics?: Record<string, any>;
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

type PuzzleTile = {
  id: string;
  index: number;
  xStart: number;
  xEnd: number;
  yStart: number;
  yEnd: number;
  status: string;
  previewReady: boolean;
};

const route = useRoute();
const config = useRuntimeConfig();
const apiBase = config.public.apiBase;
const payload = ref<DashboardPayload | null>(null);
const errorMessage = ref('');
const resultPreviewUrl = ref('');
const fragmentPreviewUrls = ref<Record<number, string>>({});
const fragmentPreviewLoading = new Set<number>();
const refreshTimer = ref<ReturnType<typeof setInterval> | null>(null);

const authHeaders = () => {
  const token = Cookies.get('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const fragments = computed<any[]>(() => Array.isArray(payload.value?.summary.fragments) ? payload.value?.summary.fragments : []);
const finalHash = computed(() => payload.value?.summary.finalHash || payload.value?.summary.reassembledHash || payload.value?.summary.expectedFullHash || '');
const splitTree = computed(() => payload.value?.summary.splitTree || payload.value?.devnet.splitTree || null);
const imageWidth = computed(() => Math.max(1, Number(payload.value?.summary.image?.width || 1280)));
const imageHeight = computed(() => Math.max(1, Number(payload.value?.summary.image?.height || 720)));
const expectedFragmentCount = computed(() => Number(payload.value?.summary.fragmentCount || fragments.value.length || 0));
const verifiedFragments = computed(() => fragments.value.filter((fragment) => fragment.verify_choice || ['verified', 'reassembled'].includes(String(fragment.status))).length);
const previewFragmentCount = computed(() => Object.keys(fragmentPreviewUrls.value).length);
const statusGridColumns = computed(() => Math.min(4, Math.max(1, expectedFragmentCount.value)));
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
const puzzleTiles = computed<PuzzleTile[]>(() => {
  return fragments.value.map((fragment, index) => ({
    id: String(fragment.fragment_id || fragment.fragment_index || index),
    index: Number(fragment.fragment_index ?? index),
    xStart: Number(fragment.x_start ?? 0),
    xEnd: Number(fragment.x_end ?? imageWidth.value),
    yStart: Number(fragment.y_start ?? 0),
    yEnd: Number(fragment.y_end ?? 0),
    status: String(fragment.status || (fragment.verify_choice ? 'verified' : 'planned')),
    previewReady: Boolean(fragment.preview_ready) || Boolean(fragment.compute_result_hash || fragment.result_hash),
  }));
});
const latestNodeRunText = computed(() => {
  const runs = Array.isArray(payload.value?.summary.nodeRuns) ? payload.value?.summary.nodeRuns : [];
  if (runs.length === 0) return payload.value?.job.errorMessage || 'Aucun node run disponible.';
  return JSON.stringify(runs[runs.length - 1], null, 2);
});
const diagnosticsText = computed(() => JSON.stringify(payload.value?.diagnostics || {}, null, 2));

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

const loadFragmentPreviews = async () => {
  const jobId = payload.value?.job.id;
  if (!jobId) return;
  const pending = puzzleTiles.value.filter((tile) => (
    tile.previewReady
    && !fragmentPreviewUrls.value[tile.index]
    && !fragmentPreviewLoading.has(tile.index)
  ));
  await Promise.allSettled(pending.map(async (tile) => {
    fragmentPreviewLoading.add(tile.index);
    try {
      const response = await fetch(`${apiBase}/jobs/${jobId}/fragments/${tile.index}/preview`, {
        headers: authHeaders(),
        cache: 'no-store',
      });
      if (!response.ok) return;
      const blob = await response.blob();
      if (!blob.type.startsWith('image/')) return;
      const previous = fragmentPreviewUrls.value[tile.index];
      if (previous) URL.revokeObjectURL(previous);
      fragmentPreviewUrls.value = {
        ...fragmentPreviewUrls.value,
        [tile.index]: URL.createObjectURL(blob),
      };
    } finally {
      fragmentPreviewLoading.delete(tile.index);
    }
  }));
};

const loadDashboard = async () => {
  errorMessage.value = '';
  try {
    payload.value = await $fetch<DashboardPayload>(`${apiBase}/jobs/${route.params.id}/dashboard`, {
      headers: authHeaders(),
    });
    await Promise.all([loadResultPreview(), loadFragmentPreviews()]);
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

const tileStatusClass = (status: string) => {
  if (status === 'reassembled' || status === 'verified') return 'border-green-400/50 bg-green-500/20 text-green-100';
  if (status === 'queued_verify') return 'border-blue-400/50 bg-blue-500/20 text-blue-100';
  if (status === 'computed') return 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100';
  if (status === 'queued_compute' || status === 'preparing') return 'border-purple-400/50 bg-purple-500/20 text-purple-100';
  if (status === 'verify_failed') return 'border-red-400/50 bg-red-500/20 text-red-100';
  return 'border-white/10 bg-black/20 text-white/60';
};

const verificationSummary = (fragment: any) => {
  const audit = fragment?.verification_result;
  if (!audit || typeof audit !== 'object' || !audit.sample_rows) return 'en attente';
  const ratio = Math.round(Number(audit.sample_ratio || 0) * 1000) / 10;
  return `${audit.sample_rows}/${audit.fragment_rows} lignes (${ratio} %) · batch #${audit.milestone_index}`;
};

const tileStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    planned: 'planifiee',
    preparing: 'preparation',
    queued_compute: 'calcul en attente',
    computed: 'pixels recus',
    queued_verify: 'verification',
    verified: 'verifiee',
    reassembled: 'assemblee',
    compute_failed: 'calcul echoue',
    verify_failed: 'verification echouee',
  };
  return labels[status] || status;
};

const tilePosition = (tile: PuzzleTile) => {
  const width = imageWidth.value;
  const height = imageHeight.value;
  const left = Math.max(0, Math.min(100, (tile.xStart / width) * 100));
  const top = Math.max(0, Math.min(100, (tile.yStart / height) * 100));
  const tileWidth = Math.max(0.25, Math.min(100 - left, ((tile.xEnd - tile.xStart) / width) * 100));
  const tileHeight = Math.max(0.25, Math.min(100 - top, ((tile.yEnd - tile.yStart) / height) * 100));
  return { left: `${left}%`, top: `${top}%`, width: `${tileWidth}%`, height: `${tileHeight}%` };
};

const tileVisualClass = (tile: PuzzleTile) => ({
  'is-ready': Boolean(fragmentPreviewUrls.value[tile.index]),
  'is-verified': tile.status === 'verified' || tile.status === 'reassembled',
  'is-active': ['preparing', 'queued_compute', 'computed', 'queued_verify'].includes(tile.status),
  'is-failed': ['compute_failed', 'verify_failed'].includes(tile.status),
});

onMounted(loadDashboard);
onBeforeUnmount(() => {
  if (refreshTimer.value) clearInterval(refreshTimer.value);
  if (resultPreviewUrl.value) URL.revokeObjectURL(resultPreviewUrl.value);
  Object.values(fragmentPreviewUrls.value).forEach((url) => URL.revokeObjectURL(url));
});
</script>

<style scoped>
.live-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  border: 1px solid rgb(248 113 113 / 45%);
  border-radius: 999px;
  background: rgb(239 68 68 / 12%);
  padding: 0.25rem 0.65rem;
  color: rgb(254 202 202);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.live-badge i {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 999px;
  background: rgb(248 113 113);
  box-shadow: 0 0 0 0 rgb(248 113 113 / 55%);
  animation: live-pulse 1.6s infinite;
}

.live-render-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 112px;
  gap: 1rem;
  align-items: stretch;
}

.live-render-stage {
  position: relative;
  overflow: hidden;
  border: 1px solid rgb(168 85 247 / 30%);
  border-radius: 1rem;
  background:
    radial-gradient(circle at 50% 45%, rgb(88 28 135 / 30%), transparent 65%),
    #07080d;
  box-shadow: 0 22px 70px rgb(0 0 0 / 38%), inset 0 0 55px rgb(168 85 247 / 8%);
}

.live-render-stage::before {
  content: '';
  position: absolute;
  inset: -35%;
  z-index: 0;
  background: conic-gradient(from 180deg, transparent, rgb(168 85 247 / 12%), transparent 32%);
  animation: stage-aura 12s linear infinite;
}

.live-render-canvas {
  position: relative;
  z-index: 1;
  width: 100%;
  overflow: hidden;
  background-color: #080910;
  background-image:
    linear-gradient(rgb(255 255 255 / 3%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(255 255 255 / 3%) 1px, transparent 1px);
  background-size: 28px 28px;
}

.live-render-tile {
  position: absolute;
  overflow: hidden;
  border: 1px solid rgb(168 85 247 / 20%);
  background: rgb(15 16 25 / 90%);
  transition: border-color 350ms ease, box-shadow 350ms ease, filter 350ms ease;
}

.live-render-tile img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: fill;
  user-select: none;
  animation: tile-reveal 700ms cubic-bezier(.2,.9,.2,1) both;
}

.live-render-tile.is-active:not(.is-ready) {
  border-color: rgb(192 132 252 / 55%);
  box-shadow: inset 0 0 24px rgb(168 85 247 / 16%);
}

.live-render-tile.is-verified {
  border-color: rgb(74 222 128 / 70%);
  box-shadow: inset 0 0 16px rgb(34 197 94 / 10%);
}

.live-render-tile.is-failed {
  border-color: rgb(248 113 113 / 80%);
  filter: saturate(0.45);
}

.tile-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.65rem;
  color: rgb(216 180 254 / 80%);
  background: linear-gradient(110deg, transparent 15%, rgb(168 85 247 / 10%) 48%, transparent 82%);
  background-size: 220% 100%;
  animation: tile-loading 2.4s linear infinite;
}

.tile-placeholder strong {
  font-size: clamp(0.65rem, 1.4vw, 1rem);
}

.tile-placeholder small {
  color: rgb(255 255 255 / 42%);
  font-size: clamp(0.5rem, 1vw, 0.72rem);
}

.tile-grid {
  position: absolute;
  inset: 0;
  opacity: 0.45;
  background-image: repeating-linear-gradient(90deg, transparent 0 11px, rgb(168 85 247 / 10%) 12px);
}

.tile-state {
  position: absolute;
  top: 50%;
  right: 0.75rem;
  z-index: 4;
  display: flex;
  align-items: center;
  gap: 0.45rem;
  transform: translateY(-50%);
  border: 1px solid rgb(255 255 255 / 12%);
  border-radius: 999px;
  background: rgb(5 6 10 / 76%);
  padding: 0.22rem 0.55rem;
  color: rgb(255 255 255 / 78%);
  font-size: 0.65rem;
  backdrop-filter: blur(8px);
  transition: opacity 180ms ease;
}

.is-ready .tile-state {
  opacity: 0;
}

.is-ready:hover .tile-state {
  opacity: 1;
}

.verified-sweep {
  position: absolute;
  inset: 0;
  z-index: 3;
  pointer-events: none;
  border-right: 2px solid rgb(74 222 128 / 75%);
  background: linear-gradient(90deg, transparent 0 85%, rgb(74 222 128 / 12%));
  animation: verified-flash 900ms ease-out both;
}

.render-scanline {
  position: absolute;
  z-index: 6;
  top: -8%;
  left: 0;
  width: 100%;
  height: 8%;
  pointer-events: none;
  opacity: 0;
  background: linear-gradient(180deg, transparent, rgb(216 180 254 / 22%), transparent);
}

.render-scanline.active {
  opacity: 1;
  animation: render-scan 4.5s linear infinite;
}

.render-vignette {
  position: absolute;
  z-index: 7;
  inset: 0;
  pointer-events: none;
  box-shadow: inset 0 0 70px rgb(0 0 0 / 48%);
}

.render-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: rgb(255 255 255 / 35%);
  font-size: 0.85rem;
  letter-spacing: 0.08em;
}

.live-render-legend {
  display: grid;
  grid-template-rows: repeat(3, 1fr);
  gap: 0.65rem;
}

.live-render-legend > div {
  display: flex;
  flex-direction: column;
  justify-content: center;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 0.85rem;
  background: rgb(0 0 0 / 18%);
  padding: 0.75rem;
}

.live-render-legend strong {
  color: white;
  font-size: 1.5rem;
  line-height: 1;
}

.live-render-legend span {
  margin-top: 0.4rem;
  color: rgb(255 255 255 / 42%);
  font-size: 0.68rem;
}

@keyframes live-pulse {
  70% { box-shadow: 0 0 0 7px rgb(248 113 113 / 0%); }
  100% { box-shadow: 0 0 0 0 rgb(248 113 113 / 0%); }
}

@keyframes stage-aura {
  to { transform: rotate(360deg); }
}

@keyframes tile-loading {
  to { background-position: -220% 0; }
}

@keyframes tile-reveal {
  from { opacity: 0; filter: brightness(2.2) saturate(0); transform: scaleX(1.018); }
  to { opacity: 1; filter: brightness(1) saturate(1); transform: scaleX(1); }
}

@keyframes verified-flash {
  from { opacity: 1; transform: translateX(-100%); }
  to { opacity: 0; transform: translateX(0); }
}

@keyframes render-scan {
  from { transform: translateY(-100%); }
  to { transform: translateY(1350%); }
}

@media (max-width: 700px) {
  .live-render-layout {
    grid-template-columns: 1fr;
  }

  .live-render-legend {
    grid-template-columns: repeat(3, 1fr);
    grid-template-rows: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .live-badge i,
  .live-render-stage::before,
  .live-render-tile img,
  .tile-placeholder,
  .verified-sweep,
  .render-scanline.active {
    animation: none;
  }
}
</style>
