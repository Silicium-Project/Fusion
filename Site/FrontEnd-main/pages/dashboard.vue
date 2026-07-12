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
          <p class="text-2xl font-bold">{{ jobs.length }}</p>
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
        <div class="flex flex-col gap-4 mb-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h3 class="text-2xl font-bold">Mes taches</h3>
            <p class="text-white/50">Le site soumet au backend, le backend orchestre Silicium, le dashboard observe le Devnet.</p>
          </div>
          <div class="flex flex-wrap items-center gap-3">
            <label class="flex h-10 items-center gap-3 rounded-lg bg-black/20 px-4 text-sm text-white/70">
              <span>Afficher les details d'erreur</span>
              <button
                type="button"
                role="switch"
                :aria-checked="showErrorDetails"
                class="relative h-6 w-11 rounded-full transition-colors"
                :class="showErrorDetails ? 'bg-red-400/70' : 'bg-white/15'"
                @click="showErrorDetails = !showErrorDetails"
              >
                <span
                  class="absolute left-1 top-1 h-4 w-4 rounded-full bg-white transition-transform"
                  :class="showErrorDetails ? 'translate-x-5' : 'translate-x-0'"
                />
              </button>
            </label>
            <button @click="loadJobs" class="h-10 px-4 rounded-lg bg-black/20 text-white/80 hover:text-white">
              Rafraichir
            </button>
          </div>
        </div>

        <div v-if="jobs.length === 0" class="text-white/50 py-6">
          Aucun job soumis pour le moment.
        </div>
        <div v-else class="space-y-3">
          <div class="flex items-center justify-between text-sm text-white/50">
            <span>{{ displayedJobs.length }} tache(s) affichee(s)</span>
            <span v-if="hiddenErrorDetails > 0">{{ hiddenErrorDetails }} detail(s) d'erreur masque(s)</span>
          </div>

          <article
            v-for="job in recentDisplayedJobs"
            :key="job.id"
            class="rounded-xl border border-white/10 bg-black/10 p-4"
          >
            <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-3">
                  <h4 class="font-semibold">{{ job.title }}</h4>
                  <span class="px-3 py-1 rounded-full text-sm" :class="statusClass(job.status)">
                    {{ job.status }}
                  </span>
                </div>
                <p class="mt-1 text-sm text-white/45">{{ job.description || 'Aucune description' }}</p>
                <p class="mt-2 break-all text-sm text-white/60">{{ job.workload }} - {{ job.siliciumJobId }}</p>
                <p class="mt-2 text-sm text-white/50">Duree : <span class="font-semibold text-white/80">{{ jobDuration(job) }}</span></p>
                <div v-if="showErrorDetails && job.errorMessage" class="mt-3 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-200">
                  {{ job.errorMessage }}
                </div>
              </div>
              <div class="flex shrink-0 gap-2">
                <button v-if="job.status === 'completed'" @click="downloadResult(job)" class="px-3 py-2 rounded-lg bg-green-500/20 text-green-200 hover:bg-green-500/30">
                  Telecharger
                </button>
                <NuxtLink :to="`/jobs/${job.id}/dashboard`" class="px-3 py-2 rounded-lg bg-blue-500/20 text-blue-200 hover:bg-blue-500/30">
                  Dashboard
                </NuxtLink>
              </div>
            </div>
          </article>

          <details v-if="olderDisplayedJobs.length > 0" class="rounded-xl border border-white/10 bg-black/10 p-4">
            <summary class="cursor-pointer select-none font-semibold text-white/80">
              Voir les anciennes taches ({{ olderDisplayedJobs.length }})
            </summary>
            <div class="mt-4 space-y-3">
              <article
                v-for="job in olderDisplayedJobs"
                :key="job.id"
                class="rounded-lg border border-white/10 bg-[#1f2029] p-4"
              >
                <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-3">
                      <h4 class="font-semibold">{{ job.title }}</h4>
                      <span class="px-3 py-1 rounded-full text-sm" :class="statusClass(job.status)">
                        {{ job.status }}
                      </span>
                    </div>
                    <p class="mt-1 text-sm text-white/45">{{ job.description || 'Aucune description' }}</p>
                    <p class="mt-2 break-all text-sm text-white/60">{{ job.workload }} - {{ job.siliciumJobId }}</p>
                    <p class="mt-2 text-sm text-white/50">Duree : <span class="font-semibold text-white/80">{{ jobDuration(job) }}</span></p>
                    <div v-if="showErrorDetails && job.errorMessage" class="mt-3 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-200">
                      {{ job.errorMessage }}
                    </div>
                  </div>
                  <div class="flex shrink-0 gap-2">
                    <button v-if="job.status === 'completed'" @click="downloadResult(job)" class="px-3 py-2 rounded-lg bg-green-500/20 text-green-200 hover:bg-green-500/30">
                      Telecharger
                    </button>
                    <NuxtLink :to="`/jobs/${job.id}/dashboard`" class="px-3 py-2 rounded-lg bg-blue-500/20 text-blue-200 hover:bg-blue-500/30">
                      Dashboard
                    </NuxtLink>
                  </div>
                </div>
              </article>
            </div>
          </details>
        </div>
      </section>

      <div class="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div class="bg-[#1f2029] rounded-2xl p-6">
          <highcharts :options="userGrowthOptions" />
        </div>
        <div class="bg-[#1f2029] rounded-2xl p-6">
          <highcharts :options="deviceTypesOptions" />
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
import { computed, reactive, ref, onBeforeUnmount, onMounted } from 'vue';
import Cookies from 'js-cookie';
import * as web3 from '@solana/web3.js';

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
  createdAt?: string;
  startedAt?: string;
  completedAt?: string;
};

const isModalOpen = ref(false);
const isSubmittingJob = ref(false);
const selectedJobFile = ref<File | null>(null);
const jobSubmitError = ref('');
const jobs = ref<Job[]>([]);
const showErrorDetails = ref(false);
const nowMs = ref(Date.now());
const clockTimer = ref<ReturnType<typeof setInterval> | null>(null);
const jobsRefreshTimer = ref<ReturnType<typeof setInterval> | null>(null);
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
});

const runningJobs = computed(() => jobs.value.filter((job) => ['queued', 'running'].includes(job.status)).length);
const completedJobs = computed(() => jobs.value.filter((job) => job.status === 'completed').length);
const hasErrorDetails = (job: Job) => Boolean(job.errorMessage);
const displayedJobs = computed(() => jobs.value);
const recentDisplayedJobs = computed(() => displayedJobs.value.slice(0, 5));
const olderDisplayedJobs = computed(() => displayedJobs.value.slice(5));
const hiddenErrorDetails = computed(() => (showErrorDetails.value ? 0 : jobs.value.filter(hasErrorDetails).length));
const latestDashboardPath = computed(() => {
  const latest = jobs.value.find((job) => job.status === 'completed') || jobs.value[0];
  return latest ? `/jobs/${latest.id}/dashboard` : '/dashboard';
});

const authHeaders = () => {
  const token = Cookies.get('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
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

const jobDuration = (job: Job) => {
  const startRaw = job.startedAt || job.createdAt;
  const start = startRaw ? Date.parse(startRaw) : NaN;
  if (!Number.isFinite(start)) return 'non disponible';
  const endRaw = job.completedAt;
  const end = endRaw ? Date.parse(endRaw) : nowMs.value;
  if (!Number.isFinite(end)) return 'en cours';
  return formatDuration((end - start) / 1000);
};

const loadJobs = async () => {
  try {
    jobs.value = await $fetch<Job[]>(`${apiBase}/jobs`, {
      headers: authHeaders(),
    });
  } catch (error) {
    console.error('Failed to fetch jobs:', error);
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
  if (status === 'failed') return 'bg-red-500/20 text-red-200';
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
  clockTimer.value = setInterval(() => {
    nowMs.value = Date.now();
  }, 1000);
  jobsRefreshTimer.value = setInterval(() => {
    if (jobs.value.some((job) => ['queued', 'running'].includes(job.status))) {
      loadJobs();
    }
  }, 3000);
  const token = Cookies.get('auth_token');
  if (!token) return;
  try {
    const fetchedUser: any = await $fetch(`${apiBase}/user`, {
      headers: authHeaders(),
    });
    user.value = fetchedUser;

    if (fetchedUser.walletAddress) {
      const connection = new web3.Connection(web3.clusterApiUrl('devnet'));
      const publicKey = new web3.PublicKey(fetchedUser.walletAddress);
      const balance = await connection.getBalance(publicKey);
      solBalance.value = balance / web3.LAMPORTS_PER_SOL;
    }
    await loadJobs();
  } catch (error) {
    console.error('Failed to fetch dashboard data:', error);
  }
});

onBeforeUnmount(() => {
  if (clockTimer.value) clearInterval(clockTimer.value);
  if (jobsRefreshTimer.value) clearInterval(jobsRefreshTimer.value);
});
</script>
