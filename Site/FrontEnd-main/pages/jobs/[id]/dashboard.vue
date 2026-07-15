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

      <div v-if="payload" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-5 mb-6">
        <div class="bg-[#1f2029] rounded-2xl p-5">
          <p class="text-white/50">Statut</p>
          <p class="text-2xl font-bold mt-2">{{ payload.job.status }}</p>
        </div>
        <div class="bg-[#1f2029] rounded-2xl p-5">
          <p class="text-white/50">Fragments resolus</p>
          <p class="text-2xl font-bold mt-2">{{ verifiedFragments }} / {{ expectedFragmentCount }}</p>
        </div>
        <div class="bg-[#1f2029] rounded-2xl p-5">
          <p class="text-white/50">Duree</p>
          <p class="text-2xl font-bold mt-2">{{ elapsedLabel }}</p>
        </div>
        <div class="bg-[#1f2029] rounded-2xl p-5">
          <p class="text-white/50">Devnet</p>
          <p class="text-2xl font-bold mt-2">{{ devnetStatusLabel }}</p>
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
        <section class="min-w-0 bg-[#1f2029] rounded-2xl p-6">
          <div class="flex flex-wrap items-center justify-between gap-4 mb-4">
            <div>
              <h2 class="text-2xl font-bold">Graphe du job</h2>
              <p class="text-white/50">Du job initial aux fragments, puis calcul, verification et reassemblage.</p>
            </div>
            <div class="flex items-center gap-2">
              <span class="mr-2 text-sm text-white/50">{{ graphFragments.length }} fragments</span>
              <button
                type="button"
                class="h-9 w-9 rounded-lg bg-white/10 text-lg hover:bg-white/15"
                aria-label="Reduire le graphe"
                @click="changeGraphZoom(-0.1)"
              >
                −
              </button>
              <span class="w-12 text-center text-xs text-white/60">{{ Math.round(graphView.scale * 100) }}%</span>
              <button
                type="button"
                class="h-9 w-9 rounded-lg bg-white/10 text-lg hover:bg-white/15"
                aria-label="Agrandir le graphe"
                @click="changeGraphZoom(0.1)"
              >
                +
              </button>
              <button
                type="button"
                class="h-9 rounded-lg bg-white/10 px-3 text-sm hover:bg-white/15"
                @click="resetGraphView"
              >
                Recentrer
              </button>
            </div>
          </div>
          <div
            ref="graphViewport"
            class="relative h-[560px] w-full touch-none select-none overflow-hidden rounded-xl border border-white/10 bg-[#f8fafc]"
            :class="graphDrag.active ? 'cursor-grabbing' : 'cursor-grab'"
            @pointerdown="startGraphDrag"
            @pointermove="moveGraphDrag"
            @pointerup="endGraphDrag"
            @pointercancel="endGraphDrag"
          >
            <div class="pointer-events-none absolute left-3 top-3 z-10 rounded-md bg-slate-900/75 px-3 py-1.5 text-xs text-white shadow">
              Glisser pour deplacer le graphe
            </div>
            <svg
              :width="jobGraph.width"
              :height="jobGraph.height"
              class="absolute left-0 top-0 block max-w-none"
              :style="graphTransformStyle"
            >
              <defs>
                <marker id="job-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
                </marker>
                <filter id="node-shadow" x="-20%" y="-20%" width="140%" height="150%">
                  <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#0f172a" flood-opacity="0.12" />
                </filter>
              </defs>
              <path
                v-for="edge in jobGraph.edges"
                :key="edge.id"
                :d="edge.path"
                fill="none"
                stroke="#94a3b8"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                marker-end="url(#job-arrow)"
              />
              <g
                v-for="node in jobGraph.nodes"
                :key="node.id"
                :transform="`translate(${node.x}, ${node.y})`"
                filter="url(#node-shadow)"
              >
                <rect
                  :width="node.width"
                  :height="node.height"
                  rx="13"
                  :fill="node.fill"
                  :stroke="node.stroke"
                  stroke-width="2"
                />
                <circle cx="16" cy="19" r="5" :fill="node.stroke" />
                <text x="29" y="24" fill="#0f172a" font-size="14" font-weight="700">{{ node.title }}</text>
                <text x="14" y="47" fill="#475569" font-size="11.5">{{ node.detail }}</text>
                <text x="14" :y="node.height - 11" :fill="node.stroke" font-size="10.5" font-weight="700">{{ node.status }}</text>
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
            <h2 class="text-2xl font-bold mb-4">Preuve blockchain</h2>
            <div class="space-y-3 text-sm">
              <div>
                <p class="text-white/50">Statut</p>
                <p class="font-semibold">{{ devnetStatusLabel }}</p>
              </div>
              <div v-if="payload.devnet.mode">
                <p class="text-white/50">Mode</p>
                <p class="font-mono break-all">{{ payload.devnet.mode }}</p>
              </div>
              <div v-if="payload.devnet.merkleRoot">
                <p class="text-white/50">Racine Merkle</p>
                <p class="font-mono break-all">{{ payload.devnet.merkleRoot }}</p>
              </div>
              <div v-if="payload.devnet.manifestHash">
                <p class="text-white/50">Hash du manifeste</p>
                <p class="font-mono break-all">{{ payload.devnet.manifestHash }}</p>
              </div>
              <div>
                <p class="text-white/50">Transaction</p>
                <p class="font-mono break-all">{{ devnetSignature || 'non disponible' }}</p>
              </div>
              <a
                v-if="payload.devnet.explorerUrl"
                :href="payload.devnet.explorerUrl"
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex rounded-lg bg-purple-500/20 px-3 py-2 text-purple-200 hover:bg-purple-500/30"
              >
                Voir sur Solana Explorer
              </a>
              <div v-if="payload.devnet.error" class="rounded-lg border border-red-400/20 bg-red-500/10 p-3 text-red-200">
                {{ payload.devnet.error }}
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
                <th class="py-3">Calcul</th>
                <th class="py-3">Verificateur</th>
                <th class="py-3">Verification</th>
                <th class="py-3">Hash resultat</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="fragment in fragments" :key="fragment.fragment_id || fragment.fragment_index" class="border-t border-white/10">
                <td class="py-4 font-mono">#{{ fragment.fragment_index }}</td>
                <td class="py-4 text-white/70">{{ fragment.parent_index ?? 'racine' }}</td>
                <td class="py-4 text-white/70 font-mono text-sm">{{ shortNode(fragment.compute_node_id || fragment.worker_output_ref?.shared_ref?.peer_id || fragment.worker_output_ref?.peer_id || 'worker') }}</td>
                <td class="py-4 text-white/70 font-mono text-sm">{{ shortNode(fragment.verify_node_id || 'en attente') }}</td>
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
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
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
    createdAt?: string;
    startedAt?: string;
    completedAt?: string;
  };
  resultReady: boolean;
  resultUrl: string;
  diagnostics?: Record<string, any>;
  summary: Record<string, any>;
  devnet: Record<string, any>;
};

type JobGraphNode = {
  id: string;
  title: string;
  detail: string;
  status: string;
  x: number;
  y: number;
  width: number;
  height: number;
  fill: string;
  stroke: string;
};

type JobGraphEdge = {
  id: string;
  path: string;
};

const route = useRoute();
const config = useRuntimeConfig();
const apiBase = config.public.apiBase;
const payload = ref<DashboardPayload | null>(null);
const errorMessage = ref('');
const resultPreviewUrl = ref('');
const refreshTimer = ref<ReturnType<typeof setInterval> | null>(null);
const clockTimer = ref<ReturnType<typeof setInterval> | null>(null);
const nowMs = ref(Date.now());
const graphViewport = ref<HTMLDivElement | null>(null);
const graphView = reactive({ x: 18, y: 26, scale: 0.65 });
const graphDrag = reactive({ active: false, pointerId: -1, startX: 0, startY: 0, originX: 0, originY: 0 });
const graphTransformStyle = computed(() => ({
  transform: `translate(${graphView.x}px, ${graphView.y}px) scale(${graphView.scale})`,
  transformOrigin: '0 0',
}));

const authHeaders = () => {
  const token = Cookies.get('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const fragments = computed<any[]>(() => Array.isArray(payload.value?.summary.fragments) ? payload.value?.summary.fragments : []);
const finalHash = computed(() => payload.value?.summary.finalHash || payload.value?.summary.reassembledHash || payload.value?.summary.expectedFullHash || '');
const startedMs = computed(() => {
  const summaryStart = Number(payload.value?.summary.startedUnix || 0);
  if (summaryStart > 0) return summaryStart * 1000;
  const fallback = payload.value?.job.startedAt || payload.value?.job.createdAt;
  const parsed = fallback ? Date.parse(fallback) : NaN;
  return Number.isFinite(parsed) ? parsed : 0;
});
const completedMs = computed(() => {
  const summaryEnd = Number(payload.value?.summary.completedUnix || 0);
  if (summaryEnd > 0) return summaryEnd * 1000;
  const parsed = payload.value?.job.completedAt ? Date.parse(payload.value.job.completedAt) : NaN;
  return Number.isFinite(parsed) ? parsed : 0;
});
const elapsedSeconds = computed(() => {
  const start = startedMs.value;
  if (!start) return 0;
  const end = completedMs.value || nowMs.value;
  return Math.max(0, Math.floor((end - start) / 1000));
});
const elapsedLabel = computed(() => formatDuration(elapsedSeconds.value));
const devnetStatus = computed(() => String(payload.value?.devnet.status || ''));
const devnetStatusLabel = computed(() => {
  if (payload.value?.devnet.ok || devnetStatus.value === 'confirmed') return 'trace OK';
  if (['pending', 'confirming', 'submitted'].includes(devnetStatus.value)) return 'en cours';
  if (devnetStatus.value === 'failed') return 'echec';
  if (!payload.value?.devnet.enabled || ['off', 'disabled', 'not_requested'].includes(devnetStatus.value)) return 'desactivee';
  return 'non confirmee';
});
const devnetSignature = computed(() => (
  payload.value?.devnet.signature
  || payload.value?.devnet.signatures?.finalize_job
  || payload.value?.job.devnetJob
  || ''
));
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
const latestNodeRunText = computed(() => {
  const runs = Array.isArray(payload.value?.summary.nodeRuns) ? payload.value?.summary.nodeRuns : [];
  if (runs.length === 0) return payload.value?.job.errorMessage || 'Aucun node run disponible.';
  return JSON.stringify(runs[runs.length - 1], null, 2);
});
const diagnosticsText = computed(() => JSON.stringify(payload.value?.diagnostics || {}, null, 2));

const graphFragments = computed<any[]>(() => {
  const sorted = [...fragments.value].sort(
    (a, b) => Number(a.fragment_index ?? 0) - Number(b.fragment_index ?? 0),
  );
  if (sorted.length > 0) return sorted;
  return Array.from({ length: expectedFragmentCount.value }, (_, index) => ({
    fragment_index: index,
    status: 'planned',
  }));
});

const jobGraph = computed(() => {
  const items = graphFragments.value;
  const nodeWidth = 174;
  const nodeHeight = 78;
  const columnGap = 28;
  const sidePadding = 56;
  const contentWidth = items.length > 0
    ? items.length * nodeWidth + Math.max(0, items.length - 1) * columnGap
    : nodeWidth;
  const width = Math.max(860, contentWidth + sidePadding * 2);
  const centerX = width / 2;
  const rootWidth = 210;
  const mergeWidth = 210;
  const nodes: JobGraphNode[] = [];
  const edges: JobGraphEdge[] = [];

  const palette = (kind: string, state: string) => {
    const failed = state.includes('failed') || state === 'error';
    if (failed) return { fill: '#fff1f2', stroke: '#ef4444' };
    if (kind === 'job') return { fill: '#f5f3ff', stroke: '#8b5cf6' };
    if (kind === 'compute') return state === 'termine'
      ? { fill: '#ecfeff', stroke: '#0891b2' }
      : { fill: '#eff6ff', stroke: '#3b82f6' };
    if (kind === 'verify') return state === 'verifie'
      ? { fill: '#ecfdf5', stroke: '#16a34a' }
      : { fill: '#fff7ed', stroke: '#f97316' };
    if (kind === 'result') return payload.value?.resultReady
      ? { fill: '#ecfdf5', stroke: '#16a34a' }
      : { fill: '#f8fafc', stroke: '#94a3b8' };
    if (kind === 'merge') return verifiedFragments.value === expectedFragmentCount.value && expectedFragmentCount.value > 0
      ? { fill: '#ecfdf5', stroke: '#16a34a' }
      : { fill: '#f8fafc', stroke: '#64748b' };
    return state === 'verified' || state === 'reassembled'
      ? { fill: '#ecfdf5', stroke: '#16a34a' }
      : { fill: '#f5f3ff', stroke: '#8b5cf6' };
  };

  const addNode = (node: Omit<JobGraphNode, 'fill' | 'stroke'>, kind: string, state: string) => {
    nodes.push({ ...node, ...palette(kind, state) });
  };
  const verticalEdge = (id: string, fromX: number, fromY: number, toX: number, toY: number) => {
    const middleY = fromY + Math.max(18, (toY - fromY) / 2);
    edges.push({ id, path: `M ${fromX} ${fromY} V ${middleY} H ${toX} V ${toY}` });
  };

  const rootX = centerX - rootWidth / 2;
  const rootY = 28;
  const rootState = String(payload.value?.job.status || 'queued');
  addNode({
    id: 'job-root',
    title: 'Job de rendu',
    detail: shortNode(payload.value?.job.siliciumJobId || payload.value?.job.title || 'Silicium'),
    status: rootState,
    x: rootX,
    y: rootY,
    width: rootWidth,
    height: nodeHeight,
  }, 'job', rootState);

  items.forEach((fragment, position) => {
    const index = Number(fragment.fragment_index ?? position);
    const x = sidePadding + position * (nodeWidth + columnGap);
    const center = x + nodeWidth / 2;
    const fragmentState = String(fragment.status || (fragment.verify_choice ? 'verified' : 'planned'));
    const computeNode = fragment.compute_node_id || fragment.computeNodeId || fragment.worker_output_ref?.shared_ref?.peer_id || fragment.worker_output_ref?.peer_id;
    const verifyNode = fragment.verify_node_id || fragment.verifyNodeId;
    const computeDone = Boolean(computeNode) || ['computed', 'queued_verify', 'verified', 'reassembled'].includes(fragmentState);
    const verifyDone = Boolean(fragment.verify_choice) || ['verified', 'reassembled'].includes(fragmentState);
    const fragmentY = 154;
    const computeY = 284;
    const verifyY = 414;

    addNode({
      id: `fragment-${index}`,
      title: `Fragment ${index}`,
      detail: `y ${Number(fragment.y_start ?? 0)} → ${Number(fragment.y_end ?? 0)}`,
      status: fragmentState,
      x,
      y: fragmentY,
      width: nodeWidth,
      height: nodeHeight,
    }, 'fragment', fragmentState);
    addNode({
      id: `compute-${index}`,
      title: 'Calcul',
      detail: computeNode ? `PC ${shortNode(computeNode)}` : 'PC en attente',
      status: computeDone ? 'termine' : 'en attente',
      x,
      y: computeY,
      width: nodeWidth,
      height: nodeHeight,
    }, 'compute', computeDone ? 'termine' : 'en attente');
    addNode({
      id: `verify-${index}`,
      title: 'Verification',
      detail: verifyNode ? `PC ${shortNode(verifyNode)}` : 'PC en attente',
      status: verifyDone ? 'verifie' : 'en attente',
      x,
      y: verifyY,
      width: nodeWidth,
      height: nodeHeight,
    }, 'verify', verifyDone ? 'verifie' : 'en attente');

    verticalEdge(`job-fragment-${index}`, centerX, rootY + nodeHeight, center, fragmentY);
    verticalEdge(`fragment-compute-${index}`, center, fragmentY + nodeHeight, center, computeY);
    verticalEdge(`compute-verify-${index}`, center, computeY + nodeHeight, center, verifyY);
  });

  const mergeY = 558;
  const resultY = 674;
  const mergeX = centerX - mergeWidth / 2;
  const allVerified = verifiedFragments.value === expectedFragmentCount.value && expectedFragmentCount.value > 0;
  addNode({
    id: 'reassembly',
    title: 'Reassemblage',
    detail: `${verifiedFragments.value} / ${expectedFragmentCount.value} fragments`,
    status: allVerified ? 'termine' : 'en attente',
    x: mergeX,
    y: mergeY,
    width: mergeWidth,
    height: nodeHeight,
  }, 'merge', allVerified ? 'termine' : 'en attente');
  addNode({
    id: 'final-result',
    title: 'Resultat final',
    detail: payload.value?.resultReady ? shortHash(finalHash.value) : 'rendu indisponible',
    status: payload.value?.resultReady ? 'disponible' : 'en attente',
    x: mergeX,
    y: resultY,
    width: mergeWidth,
    height: nodeHeight,
  }, 'result', payload.value?.resultReady ? 'disponible' : 'en attente');

  items.forEach((fragment, position) => {
    const index = Number(fragment.fragment_index ?? position);
    const center = sidePadding + position * (nodeWidth + columnGap) + nodeWidth / 2;
    verticalEdge(`verify-merge-${index}`, center, 414 + nodeHeight, centerX, mergeY);
  });
  verticalEdge('merge-result', centerX, mergeY + nodeHeight, centerX, resultY);

  return { width, height: 790, nodes, edges };
});

const clampGraphScale = (value: number) => Math.max(0.35, Math.min(1.35, value));

const changeGraphZoom = (delta: number) => {
  const viewport = graphViewport.value;
  const previousScale = graphView.scale;
  const nextScale = clampGraphScale(previousScale + delta);
  if (!viewport || nextScale === previousScale) return;
  const centerX = viewport.clientWidth / 2;
  const centerY = viewport.clientHeight / 2;
  const contentX = (centerX - graphView.x) / previousScale;
  const contentY = (centerY - graphView.y) / previousScale;
  graphView.scale = nextScale;
  graphView.x = centerX - contentX * nextScale;
  graphView.y = centerY - contentY * nextScale;
};

const resetGraphView = async () => {
  await nextTick();
  const viewport = graphViewport.value;
  if (!viewport) return;
  const fitScale = (viewport.clientWidth - 36) / Math.max(1, jobGraph.value.width);
  graphView.scale = clampGraphScale(Math.max(0.55, Math.min(0.82, fitScale)));
  const renderedWidth = jobGraph.value.width * graphView.scale;
  const renderedHeight = jobGraph.value.height * graphView.scale;
  graphView.x = renderedWidth <= viewport.clientWidth
    ? (viewport.clientWidth - renderedWidth) / 2
    : 18;
  graphView.y = Math.max(18, (viewport.clientHeight - renderedHeight) / 2);
};

const startGraphDrag = (event: PointerEvent) => {
  if (event.button !== 0) return;
  const target = event.currentTarget as HTMLElement;
  target.setPointerCapture(event.pointerId);
  graphDrag.active = true;
  graphDrag.pointerId = event.pointerId;
  graphDrag.startX = event.clientX;
  graphDrag.startY = event.clientY;
  graphDrag.originX = graphView.x;
  graphDrag.originY = graphView.y;
};

const moveGraphDrag = (event: PointerEvent) => {
  if (!graphDrag.active || event.pointerId !== graphDrag.pointerId) return;
  graphView.x = graphDrag.originX + event.clientX - graphDrag.startX;
  graphView.y = graphDrag.originY + event.clientY - graphDrag.startY;
};

const endGraphDrag = (event: PointerEvent) => {
  if (!graphDrag.active || event.pointerId !== graphDrag.pointerId) return;
  const target = event.currentTarget as HTMLElement;
  if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId);
  graphDrag.active = false;
  graphDrag.pointerId = -1;
};

watch(() => jobGraph.value.width, resetGraphView, { flush: 'post' });

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

const shortNode = (value: any) => {
  const text = String(value || '').trim();
  if (!text) return 'non disponible';
  if (text.length <= 22) return text;
  return `${text.slice(0, 12)}...${text.slice(-6)}`;
};

const formatDuration = (seconds: number) => {
  const safeSeconds = Math.max(0, Math.floor(seconds || 0));
  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = safeSeconds % 60;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours > 0) return `${hours}h ${String(remainingMinutes).padStart(2, '0')}m ${String(remainingSeconds).padStart(2, '0')}s`;
  if (minutes > 0) return `${minutes}m ${String(remainingSeconds).padStart(2, '0')}s`;
  return `${remainingSeconds}s`;
};

const tileClass = (status: string) => {
  if (status === 'reassembled' || status === 'verified') return 'border-green-400/50 bg-green-500/20 text-green-100';
  if (status === 'queued_verify') return 'border-blue-400/50 bg-blue-500/20 text-blue-100';
  if (status === 'computed') return 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100';
  if (status === 'queued_compute' || status === 'preparing') return 'border-purple-400/50 bg-purple-500/20 text-purple-100';
  if (status === 'verify_failed') return 'border-red-400/50 bg-red-500/20 text-red-100';
  return 'border-white/10 bg-black/20 text-white/60';
};

onMounted(() => {
  clockTimer.value = setInterval(() => {
    nowMs.value = Date.now();
  }, 1000);
  loadDashboard();
});
onBeforeUnmount(() => {
  if (refreshTimer.value) clearInterval(refreshTimer.value);
  if (clockTimer.value) clearInterval(clockTimer.value);
  if (resultPreviewUrl.value) URL.revokeObjectURL(resultPreviewUrl.value);
});
</script>
