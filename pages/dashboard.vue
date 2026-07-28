<template>
  <div class="min-h-screen bg-[#131419] text-white flex">
    <nav class="w-64 bg-[#1f2029] p-4 flex flex-col justify-between border-r border-black/20">
      <div>
        <div class="p-4 mb-4">
          <h1 class="text-3xl font-extrabold">
            <span class="text-transparent bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text">Silicium</span>
          </h1>
        </div>
        <ul class="space-y-2">
          <li>
            <NuxtLink to="/" class="flex items-center text-lg text-white/60 hover:text-white hover:bg-black/20 p-3 rounded-xl transition-colors">
              <img src="~assets/icons/Products.svg" alt="" class="w-6 h-6 mr-4" />
              Accueil
            </NuxtLink>
          </li>
          <li>
            <a href="#" class="flex items-center text-lg font-semibold p-3 rounded-xl bg-gradient-to-r from-purple-500/20 to-blue-500/20">
              <img src="~assets/icons/Users.svg" alt="" class="w-6 h-6 mr-4" />
              Tableau de bord
            </a>
          </li>
          <li>
            <a href="#jobs" class="flex items-center text-lg text-white/60 hover:text-white hover:bg-black/20 p-3 rounded-xl transition-colors">
              <img src="~assets/icons/Receipt.svg" alt="" class="w-6 h-6 mr-4" />
              Mes taches
            </a>
          </li>
          <li>
            <NuxtLink :to="latestDashboardPath" class="flex items-center text-lg text-white/60 hover:text-white hover:bg-black/20 p-3 rounded-xl transition-colors">
              <img src="~assets/icons/Transactions.svg" alt="" class="w-6 h-6 mr-4" />
              Dashboard
            </NuxtLink>
          </li>
          <li>
            <a href="#" class="flex items-center text-lg text-white/60 hover:text-white hover:bg-black/20 p-3 rounded-xl transition-colors">
              <img src="~assets/icons/Products.svg" alt="" class="w-6 h-6 mr-4" />
              Mes appareils
            </a>
          </li>
        </ul>
      </div>
      <div class="p-4">
        <button @click="isModalOpen = true" class="w-full h-12 rounded-xl bg-gradient-to-r from-purple-400 to-blue-400 font-bold text-lg hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg">
          Soumettre une tache
        </button>
      </div>
    </nav>

    <main class="flex-1 p-10 relative">
      <div class="absolute top-10 right-10 bg-black/20 rounded-lg p-2 flex items-center space-x-4">
        <div v-if="solBalance !== null" class="font-semibold pl-2">
          {{ solBalance.toFixed(4) }} SOL
        </div>
        <span v-if="solBalance !== null" class="text-white/30">|</span>
        <NuxtLink to="/profile" class="flex items-center space-x-3">
          <div class="w-10 h-10 rounded-full bg-gradient-to-r from-purple-400 to-blue-400 flex items-center justify-center font-bold text-xl">
            {{ user ? (user.username || user.email)?.[0].toUpperCase() : '' }}
          </div>
          <span class="font-semibold pr-2">{{ user?.username || user?.email }}</span>
        </NuxtLink>
      </div>

      <h2 class="text-4xl font-bold mb-2">Tableau de bord</h2>
      <p class="text-lg text-white/50 mb-10">Soumission, suivi et resultats des calculs Silicium.</p>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div class="bg-[#1f2029] rounded-2xl p-6">
          <p class="text-white/50">Jobs</p>
          <p class="text-2xl font-bold">{{ totalJobs }}</p>
        </div>
        <div class="bg-[#1f2029] rounded-2xl p-6">
          <p class="text-white/50">En cours</p>
          <p class="text-2xl font-bold">{{ runningJobs }}</p>
        </div>
        <div class="bg-[#1f2029] rounded-2xl p-6">
          <p class="text-white/50">Termines</p>
          <p class="text-2xl font-bold">{{ completedJobs }}</p>
        </div>
        <div class="bg-[#1f2029] rounded-2xl p-6">
          <p class="text-white/50">Devnet</p>
          <a :href="devnetDashboardUrl" target="_blank" rel="noopener" class="text-blue-300 hover:text-blue-200 font-semibold">
            Ouvrir
          </a>
        </div>
      </div>

      <section id="jobs" class="mt-8 bg-[#1f2029] rounded-2xl p-6">
        <div class="flex flex-wrap items-center justify-between gap-4 mb-4">
          <div>
            <h3 class="text-2xl font-bold">Mes taches</h3>
            <p class="text-white/50">Le site soumet au backend, le backend orchestre Silicium, le dashboard observe le Devnet.</p>
          </div>
          <div class="flex items-center gap-2">
            <select v-model="statusFilter" class="h-10 rounded-lg bg-black/20 px-3 text-white/80" @change="changeFilter">
              <option value="all" class="bg-[#1f2029]">Tous les statuts</option>
              <option value="running" class="bg-[#1f2029]">En cours</option>
              <option value="queued" class="bg-[#1f2029]">En attente</option>
              <option value="completed" class="bg-[#1f2029]">Terminés</option>
              <option value="failed" class="bg-[#1f2029]">Échoués</option>
              <option value="cancelled" class="bg-[#1f2029]">Annulés</option>
              <option value="expired" class="bg-[#1f2029]">Expirés</option>
            </select>
            <button @click="loadJobs" class="h-10 px-4 rounded-lg bg-black/20 text-white/80 hover:text-white">Rafraichir</button>
          </div>
        </div>

        <div v-if="jobs.length === 0" class="text-white/50 py-6">
          Aucun job soumis pour le moment.
        </div>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-left">
            <thead class="text-white/50 text-sm">
              <tr>
                <th class="py-3">Nom</th>
                <th class="py-3">Workload</th>
                <th class="py-3">Statut</th>
                <th class="py-3">Job reseau</th>
                <th class="py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="job in jobs" :key="job.id" class="border-t border-white/10">
                <td class="py-4">
                  <div class="font-semibold">{{ job.title }}</div>
                  <div class="text-white/40 text-sm">{{ job.description }}</div>
                  <div v-if="job.errorMessage" class="text-red-300 text-sm mt-1 max-w-xl truncate" :title="job.errorMessage">
                    {{ compactError(job.errorMessage) }}
                  </div>
                </td>
                <td class="py-4 text-white/70">{{ job.workload }}</td>
                <td class="py-4">
                  <span class="px-3 py-1 rounded-full text-sm" :class="statusClass(job.status)">
                    {{ job.status }}
                  </span>
                </td>
                <td class="py-4 text-white/70">{{ job.siliciumJobId }}</td>
                <td class="py-4">
                  <div class="flex justify-end gap-2">
                    <button v-if="job.status === 'completed'" @click="downloadResult(job)" class="px-3 py-2 rounded-lg bg-green-500/20 text-green-200 hover:bg-green-500/30">
                      Telecharger
                    </button>
                    <NuxtLink :to="`/jobs/${job.id}/dashboard`" class="px-3 py-2 rounded-lg bg-blue-500/20 text-blue-200 hover:bg-blue-500/30">
                      Dashboard
                    </NuxtLink>
                    <button
                      v-if="isCancellable(job)"
                      :disabled="cancellingJobId === job.id"
                      class="px-3 py-2 rounded-lg bg-red-500/20 text-red-200 hover:bg-red-500/30 disabled:opacity-50"
                      @click="cancelJob(job)"
                    >
                      {{ cancellingJobId === job.id ? 'Arrêt…' : 'Annuler' }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="totalPages > 1" class="mt-5 flex items-center justify-between border-t border-white/10 pt-4">
          <span class="text-sm text-white/50">Page {{ currentPage }} / {{ totalPages }} · {{ totalJobs }} tâches</span>
          <div class="flex gap-2">
            <button :disabled="currentPage <= 1" class="px-3 py-2 rounded-lg bg-black/20 disabled:opacity-30" @click="goToPage(currentPage - 1)">Précédente</button>
            <button :disabled="currentPage >= totalPages" class="px-3 py-2 rounded-lg bg-black/20 disabled:opacity-30" @click="goToPage(currentPage + 1)">Suivante</button>
          </div>
        </div>
      </section>

      <section class="mt-8 bg-[#1f2029] rounded-2xl p-6">
        <div class="flex items-center justify-between mb-4">
          <div><h3 class="text-2xl font-bold">Taches reseau RPC</h3><p class="text-white/50">Registre canonique du VPS, y compris les executions hors job du site.</p></div>
          <button @click="loadNetworkTasks" class="h-10 px-4 rounded-lg bg-black/20 text-white/80 hover:text-white">Rafraichir</button>
        </div>
        <div v-if="networkTasks.length === 0" class="text-white/50">Aucune tache RPC.</div>
        <div v-else class="overflow-x-auto"><table class="w-full text-left"><thead class="text-white/50 text-sm"><tr><th class="py-3">Travail</th><th class="py-3">Workload</th><th class="py-3">Statut</th><th class="py-3">Progression</th><th class="py-3">Sous-taches</th></tr></thead><tbody><tr v-for="task in networkTasks" :key="task.work_id" class="border-t border-white/10"><td class="py-3 font-mono text-sm">{{ task.work_id }}</td><td class="py-3 text-white/70">{{ task.workload || task.kind || 'compute' }}</td><td class="py-3"><span class="px-3 py-1 rounded-full text-sm" :class="statusClass(task.status)">{{ task.status }}</span></td><td class="py-3 text-white/70">{{ task.completed }}/{{ task.total }}</td><td class="py-3 text-white/70">{{ task.total }} ({{ task.active }} active)</td></tr></tbody></table></div>
      </section>

      <div class="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div class="lg:col-span-2">
          <NetworkGraph :api-base="apiBase" />
        </div>
        <div class="bg-[#1f2029] rounded-2xl p-6">
          <ClientOnly>
            <highcharts :options="deviceTypesOptions" />
            <template #fallback><div class="flex items-center justify-center h-full text-white/20 text-sm">Chargement...</div></template>
          </ClientOnly>
        </div>
      </div>

      <div v-if="isModalOpen" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div class="bg-[#1f2029] rounded-2xl p-8 w-full max-w-lg">
          <div class="flex justify-between items-center mb-6">
            <h3 class="text-2xl font-bold">Soumettre une tache</h3>
            <button @click="isModalOpen = false" class="text-white/50 hover:text-white">
              <span class="text-2xl leading-none">&times;</span>
            </button>
          </div>
          <form @submit.prevent="submitJob">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
              <label class="block">
                <span class="block text-white/50 mb-2">Type de tache</span>
                <select v-model="jobForm.workload" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white focus:outline-none focus:ring-2 focus:ring-purple-400">
                  <option v-for="option in workloadOptions" :key="option.value" :value="option.value" class="bg-[#1f2029] text-white">
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label class="block">
                <span class="block text-white/50 mb-2">Priorite</span>
                <select v-model="jobForm.priority" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white focus:outline-none focus:ring-2 focus:ring-purple-400">
                  <option v-for="option in priorityOptions" :key="option.value" :value="option.value" class="bg-[#1f2029] text-white">
                    {{ option.label }}
                  </option>
                </select>
              </label>
            </div>
            <label v-if="jobForm.workload === 'raytracer'" class="block mb-6">
              <span class="flex items-center justify-between text-white/50 mb-2">
                <span>Nombre de parcelles</span>
                <strong class="text-purple-200">{{ jobForm.fragmentCount }}</strong>
              </span>
              <input
                v-model.number="jobForm.fragmentCount"
                type="range"
                min="1"
                max="256"
                step="1"
                class="w-full accent-purple-400"
              >
              <span class="block text-xs text-white/35 mt-2">Les parcelles sont lancees depuis le centre, puis de proche en proche.</span>
            </label>
            <label class="block mb-6">
              <span class="flex items-center justify-between text-white/50 mb-2">
                <span>Durée maximale</span>
                <strong class="text-purple-200">{{ Math.round(jobForm.maxRuntimeSeconds / 60) }} min</strong>
              </span>
              <input v-model.number="jobForm.maxRuntimeSeconds" type="range" min="60" max="14400" step="60" class="w-full accent-purple-400">
              <span class="block text-xs text-white/35 mt-2">À l’échéance, l’arrêt signé est propagé à tout le réseau.</span>
            </label>
            <input v-model="jobForm.title" type="text" placeholder="Nom de la tache" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400 mb-6">
            <textarea v-model="jobForm.description" placeholder="Description" class="w-full h-24 bg-black/20 rounded-lg px-4 py-2 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400 mb-6"></textarea>
            <div class="mb-6">
              <label for="file-input" class="block text-white/50 mb-2">Fichier d'entree</label>
              <input id="file-input" type="file" accept=".json,.cfg,application/json,text/plain" class="w-full text-white" @change="onJobFileChange">
            </div>
            <p v-if="jobSubmitError" class="text-red-300 mb-4">{{ jobSubmitError }}</p>
            <button type="submit" :disabled="isSubmittingJob" class="w-full h-12 rounded-lg bg-gradient-to-r from-purple-400 to-blue-400 font-bold text-lg hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg disabled:opacity-50">
              {{ isSubmittingJob ? 'Envoi en cours' : 'Envoyer' }}
            </button>
          </form>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, onMounted } from 'vue';
import Cookies from 'js-cookie';
import { clampJobPage, compactJobError, isJobCancellable } from '~/utils/jobs';

type Job = {
  id: number;
  title: string;
  description: string;
  workload: string;
  priority: string;
  status: string;
  siliciumJobId: string;
  dashboardUrl?: string;
  errorMessage?: string;
};

const isModalOpen = ref(false);
const isSubmittingJob = ref(false);
const selectedJobFile = ref<File | null>(null);
const jobSubmitError = ref('');
const jobs = ref<Job[]>([]);
const networkTasks = ref<any[]>([]);
const totalJobs = ref(0);
const currentPage = ref(1);
const pageSize = 20;
const statusFilter = ref('all');
const cancellingJobId = ref<number | null>(null);
const user = ref<any>(null);
const solBalance = ref<number | null>(null);
const config = useRuntimeConfig();
const apiBase = config.public.apiBase;
const devnetDashboardUrl = config.public.devnetDashboardUrl;

const workloadOptions = [
  { value: 'raytracer', label: 'Raytracer' },
];

const priorityOptions = [
  { value: 'high', label: 'Haute' },
  { value: 'normal', label: 'Normale' },
  { value: 'low', label: 'Basse' },
  { value: 'urgent', label: 'Urgente' },
];

const jobForm = reactive({
  workload: 'raytracer',
  priority: 'high',
  title: 'Raytracer',
  description: '',
  fragmentCount: 64,
  maxRuntimeSeconds: 3600,
});

const runningJobs = computed(() => jobs.value.filter((job) => ['queued', 'running'].includes(job.status)).length);
const completedJobs = computed(() => jobs.value.filter((job) => job.status === 'completed').length);
const latestDashboardPath = computed(() => {
  const latest = jobs.value.find((job) => job.status === 'completed') || jobs.value[0];
  return latest ? `/jobs/${latest.id}/dashboard` : '/dashboard';
});
const totalPages = computed(() => Math.max(1, Math.ceil(totalJobs.value / pageSize)));

const authHeaders = () => {
  const token = Cookies.get('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const loadJobs = async () => {
  try {
    const response = await $fetch.raw<Job[]>(`${apiBase}/jobs`, {
      headers: authHeaders(),
      query: {
        page: currentPage.value,
        page_size: pageSize,
        status: statusFilter.value,
      },
    });
    jobs.value = response._data || [];
    totalJobs.value = Number(response.headers.get('x-total-count') || jobs.value.length);
  } catch (error) {
    console.error('Failed to fetch jobs:', error);
  }
};

const loadNetworkTasks = async () => {
  try {
    const payload = await $fetch<{ active: any[]; recent: any[] }>(`${apiBase}/jobs/network/tasks`, { headers: authHeaders() });
    networkTasks.value = payload.workloads || [];
  } catch (error) { console.error('Failed to fetch network tasks:', error); }
};

const goToPage = async (page: number) => {
  currentPage.value = clampJobPage(page, totalJobs.value, pageSize);
  await loadJobs();
};

const changeFilter = async () => {
  currentPage.value = 1;
  await loadJobs();
};

const compactError = compactJobError;

const isCancellable = (job: Job) => isJobCancellable(job.status);

const cancelJob = async (job: Job) => {
  if (!window.confirm(`Annuler « ${job.title} » ? Le travail déjà vérifié restera facturable.`)) return;
  cancellingJobId.value = job.id;
  try {
    await $fetch(`${apiBase}/jobs/${job.id}/cancel`, {
      method: 'POST',
      headers: authHeaders(),
      body: { reason: 'cancelled from web dashboard' },
    });
    await loadJobs();
  } catch (error) {
    console.error('Failed to cancel job:', error);
  } finally {
    cancellingJobId.value = null;
  }
};

const onJobFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement;
  selectedJobFile.value = input.files?.[0] || null;
};

const submitJob = async () => {
  jobSubmitError.value = '';
  if (!selectedJobFile.value) {
    jobSubmitError.value = 'Ajoute un fichier de configuration.';
    return;
  }
  isSubmittingJob.value = true;
  try {
    const formData = new FormData();
    formData.append('file', selectedJobFile.value);
    formData.append('workload', jobForm.workload);
    formData.append('priority', jobForm.priority);
    formData.append('title', jobForm.title);
    formData.append('description', jobForm.description);
    formData.append('fragment_count', String(jobForm.fragmentCount));
    formData.append('max_runtime_seconds', String(jobForm.maxRuntimeSeconds));
    await $fetch(`${apiBase}/jobs`, {
      method: 'POST',
      headers: authHeaders(),
      body: formData,
    });
    isModalOpen.value = false;
    selectedJobFile.value = null;
    await loadJobs();
  } catch (error: any) {
    jobSubmitError.value = error?.data || error?.message || 'Impossible de soumettre la tache.';
  } finally {
    isSubmittingJob.value = false;
  }
};

const downloadResult = async (job: Job) => {
  try {
    const response = await fetch(`${apiBase}/jobs/${job.id}/result`, {
      headers: authHeaders(),
    });
    if (!response.ok) throw new Error('Result is not ready');
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${job.siliciumJobId || `job-${job.id}`}-result.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  } catch (error) {
    console.error('Failed to download result:', error);
  }
};

const statusClass = (status: string) => {
  if (status === 'completed') return 'bg-green-500/20 text-green-200';
  if (['failed', 'expired'].includes(status)) return 'bg-red-500/20 text-red-200';
  if (['cancelled', 'cancelling'].includes(status)) return 'bg-orange-500/20 text-orange-200';
  if (status === 'running') return 'bg-blue-500/20 text-blue-200';
  return 'bg-yellow-500/20 text-yellow-200';
};

const userGrowthOptions = ref({
  chart: { type: 'line', backgroundColor: 'transparent' },
  title: { text: 'Evolution des utilisateurs', style: { color: '#ffffff' } },
  xAxis: { categories: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'], labels: { style: { color: '#ffffff' } } },
  yAxis: { title: { text: 'Nombre d utilisateurs', style: { color: '#ffffff' } }, labels: { style: { color: '#ffffff' } } },
  series: [{ name: 'Utilisateurs', data: [120, 250, 400, 580, 800, 1050], color: '#8b5cf6' }],
  legend: { itemStyle: { color: '#ffffff' } },
});

const deviceTypesOptions = ref({
  chart: { type: 'pie', backgroundColor: 'transparent' },
  title: { text: 'Types d appareils connectes', style: { color: '#ffffff' } },
  tooltip: { pointFormat: '{series.name}: <b>{point.percentage:.1f}%</b>' },
  plotOptions: {
    pie: {
      allowPointSelect: true,
      cursor: 'pointer',
      dataLabels: { enabled: true, format: '<b>{point.name}</b>: {point.percentage:.1f} %', style: { color: 'white' } },
    },
  },
  series: [{
    name: 'Types',
    colorByPoint: true,
    data: [
      { name: 'CPU', y: 70, color: '#8b5cf6' },
      { name: 'GPU', y: 20, color: '#3b82f6' },
      { name: 'ASIC', y: 10, color: '#10b981' },
    ],
  }],
  legend: { itemStyle: { color: '#ffffff' } },
});

onMounted(async () => {
  const token = Cookies.get('auth_token');
  if (!token) return;
  try {
    const fetchedUser: any = await $fetch(`${apiBase}/user`, {
      headers: authHeaders(),
    });
    user.value = fetchedUser;

    if (fetchedUser.walletAddress) {
      const web3 = await import('@solana/web3.js');
      const connection = new web3.Connection(web3.clusterApiUrl('devnet'));
      const publicKey = new web3.PublicKey(fetchedUser.walletAddress);
      const balance = await connection.getBalance(publicKey);
      solBalance.value = balance / web3.LAMPORTS_PER_SOL;
    }
    await loadJobs();
    await loadNetworkTasks();
  } catch (error) {
    console.error('Failed to fetch dashboard data:', error);
  }
});
</script>
