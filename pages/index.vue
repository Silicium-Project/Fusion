<template>
  <div class="relative min-h-screen overflow-hidden bg-[#070912] text-white">
    <div class="absolute inset-0">
      <div class="absolute left-[-10%] top-[-10%] h-[34rem] w-[34rem] rounded-full bg-cyan-500/12 blur-3xl"></div>
      <div class="absolute right-[-12%] top-[10%] h-[30rem] w-[30rem] rounded-full bg-fuchsia-500/12 blur-3xl"></div>
      <div class="absolute bottom-[-12%] left-[20%] h-[28rem] w-[28rem] rounded-full bg-emerald-500/10 blur-3xl"></div>
    </div>

    <Header @register="handleRegister" />

    <main class="relative z-10 mx-auto max-w-7xl px-6 pb-20 pt-28 md:px-8 lg:pb-24">
      <section class="grid items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
        <div>
          <span class="inline-flex items-center rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] text-cyan-200">
            Verification automatique toutes les 30s
          </span>
          <h1 class="mt-6 max-w-3xl text-5xl font-black leading-none md:text-7xl">
            Le site, les services VPS et le canal de mise a jour dans une seule vue.
          </h1>
          <p class="mt-6 max-w-2xl text-lg leading-8 text-white/72 md:text-xl">
            Silicium expose ici l'etat public du backend, du manifeste de release et des liens de distribution.
            Le backend et le bridge sont verifies sur le VPS, tandis que la home se rafraichit automatiquement.
          </p>

          <div class="mt-8 flex flex-wrap gap-3">
            <NuxtLink
              to="/dashboard"
              class="inline-flex items-center rounded-full bg-white px-6 py-3 text-sm font-bold text-slate-950 transition hover:scale-[1.02]"
            >
              Ouvrir le dashboard
            </NuxtLink>
            <a
              :href="nodeAppWindowsUrl"
              class="inline-flex items-center rounded-full border border-white/15 bg-white/5 px-6 py-3 text-sm font-semibold text-white/85 transition hover:border-white/30 hover:bg-white/10"
              download
            >
              Telecharger le node Windows
            </a>
            <a
              :href="updateManifestUrl"
              class="inline-flex items-center rounded-full border border-cyan-400/25 bg-cyan-400/10 px-6 py-3 text-sm font-semibold text-cyan-100 transition hover:border-cyan-300/40 hover:bg-cyan-400/15"
              target="_blank"
              rel="noreferrer"
            >
              Ouvrir le manifeste
            </a>
          </div>

          <div class="mt-10 grid gap-4 sm:grid-cols-3">
            <article class="rounded-3xl border border-white/10 bg-white/5 p-5 shadow-2xl shadow-black/20 backdrop-blur">
              <p class="text-xs uppercase tracking-[0.24em] text-white/40">Backend</p>
              <p class="mt-3 text-2xl font-extrabold" :class="backendHealthy ? 'text-emerald-300' : 'text-rose-300'">
                {{ backendHealthy ? 'En ligne' : 'Hors ligne' }}
              </p>
              <p class="mt-2 text-sm text-white/55">{{ backendDetail }}</p>
            </article>
            <article class="rounded-3xl border border-white/10 bg-white/5 p-5 shadow-2xl shadow-black/20 backdrop-blur">
              <p class="text-xs uppercase tracking-[0.24em] text-white/40">Frontend</p>
              <p class="mt-3 text-2xl font-extrabold text-cyan-300">Actif</p>
              <p class="mt-2 text-sm text-white/55">La page publique est servie par le proxy VPS.</p>
            </article>
            <article class="rounded-3xl border border-white/10 bg-white/5 p-5 shadow-2xl shadow-black/20 backdrop-blur">
              <p class="text-xs uppercase tracking-[0.24em] text-white/40">Release</p>
              <p class="mt-3 text-2xl font-extrabold" :class="manifest ? 'text-fuchsia-300' : 'text-amber-300'">
                {{ manifestLabel }}
              </p>
              <p class="mt-2 text-sm text-white/55">{{ manifestDetail }}</p>
            </article>
          </div>
        </div>

        <aside class="rounded-[2rem] border border-white/10 bg-slate-950/65 p-6 shadow-[0_30px_80px_rgba(0,0,0,0.45)] backdrop-blur-xl">
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="text-xs uppercase tracking-[0.28em] text-white/40">Live status</p>
              <h2 class="mt-3 text-2xl font-black">Services exposes</h2>
            </div>
            <button
              class="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs font-semibold text-white/75 transition hover:border-white/25 hover:bg-white/10"
              @click="refreshStatus"
            >
              Rafraichir
            </button>
          </div>

          <div class="mt-6 space-y-3">
            <article
              v-for="service in services"
              :key="service.name"
              class="rounded-2xl border border-white/8 bg-white/5 p-4 transition hover:border-white/15"
            >
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="font-semibold">{{ service.name }}</p>
                  <p class="mt-1 text-sm text-white/50">{{ service.description }}</p>
                </div>
                <span
                  class="rounded-full px-3 py-1 text-xs font-bold"
                  :class="statusBadgeClass(service.status)"
                >
                  {{ service.statusLabel }}
                </span>
              </div>
              <p class="mt-3 text-sm text-white/70">{{ service.detail }}</p>
            </article>
          </div>

          <div class="mt-6 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-4">
            <p class="text-xs uppercase tracking-[0.24em] text-cyan-200/70">Derniere verification</p>
            <p class="mt-2 text-sm text-cyan-50">{{ lastCheckedLabel }}</p>
            <p class="mt-1 text-xs text-cyan-100/60">
              Le statut est repasse automatiquement toutes les {{ refreshSeconds }} secondes.
            </p>
          </div>

          <div v-if="manifestChannels.length" class="mt-6">
            <p class="text-xs uppercase tracking-[0.24em] text-white/40">Canaux de mise a jour</p>
            <div class="mt-3 grid gap-3">
              <article
                v-for="channel in manifestChannels"
                :key="channel.name"
                class="rounded-2xl border border-white/8 bg-black/20 p-4"
              >
                <div class="flex items-center justify-between gap-3">
                  <div>
                    <p class="font-semibold capitalize">{{ channel.name }}</p>
                    <p class="mt-1 text-xs text-white/45">{{ channel.url }}</p>
                  </div>
                  <span class="rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-white/70">
                    {{ channel.version }}
                  </span>
                </div>
                <p class="mt-2 text-xs text-white/55">build {{ channel.build || 'unknown' }}</p>
              </article>
            </div>
          </div>
        </aside>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useRouter } from '#vue-router';
import Cookies from 'js-cookie';
import { jwtDecode } from 'jwt-decode';
import Header from '../components/Header.vue';
import '~/assets/css/stars.css';

type UpdateChannel = {
  version?: string;
  build?: string;
  url?: string;
};

type UpdateManifest = {
  generated_utc?: string;
  channels?: Record<string, UpdateChannel>;
};

type ServiceStatus = 'up' | 'down' | 'loading';

const router = useRouter();
const { public: publicConfig } = useRuntimeConfig();
const apiBase = publicConfig.apiBase;
const updateManifestUrl = publicConfig.updateManifestUrl || '/downloads/update-manifest.json';
const nodeAppWindowsUrl = publicConfig.nodeAppWindowsUrl;
const refreshSeconds = Number(publicConfig.statusRefreshSeconds || 30);

const backendHealthy = ref(false);
const backendDetail = ref('En attente de la premiere verification.');
const manifest = ref<UpdateManifest | null>(null);
const manifestError = ref('');
const lastChecked = ref<string>('');
const refreshTimer = ref<number | null>(null);

const manifestChannels = computed(() =>
  Object.entries(manifest.value?.channels || {}).map(([name, channel]) => ({
    name,
    version: channel?.version || 'unknown',
    build: channel?.build || '',
    url: channel?.url || updateManifestUrl,
  })),
);

const manifestLabel = computed(() => {
  if (!manifest.value) return manifestError.value ? 'Indisponible' : 'Chargement';
  return manifest.value.generated_utc ? 'Actif' : 'Aucun horodatage';
});

const manifestDetail = computed(() => {
  if (manifestError.value) return manifestError.value;
  if (manifest.value?.generated_utc) return `Genere le ${formatDateTime(manifest.value.generated_utc)}`;
  return 'Le manifeste de release est en cours de chargement.';
});

const lastCheckedLabel = computed(() =>
  lastChecked.value ? formatDateTime(lastChecked.value) : 'Aucune verification effectuee.',
);

const services = computed(() => [
  {
    name: 'Frontend web',
    description: 'Landing page publique et navigation initiale',
    status: 'up' as ServiceStatus,
    statusLabel: 'Actif',
    detail: 'Le site est servi par le proxy VPS.',
  },
  {
    name: 'Backend API',
    description: 'Healthcheck et logique applicative',
    status: backendHealthy.value ? 'up' : 'down',
    statusLabel: backendHealthy.value ? 'En ligne' : 'Hors ligne',
    detail: backendDetail.value,
  },
  {
    name: 'Update manifest',
    description: 'Canal de mise a jour publie sur le VPS',
    status: manifest.value ? 'up' : 'loading',
    statusLabel: manifest.value ? 'Disponible' : 'En attente',
    detail: manifestDetail.value,
  },
]);

function handleRegister() {
  router.push('/auth');
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat('fr-FR', {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(date);
}

function statusBadgeClass(status: ServiceStatus) {
  if (status === 'up') return 'bg-emerald-400/15 text-emerald-200';
  if (status === 'down') return 'bg-rose-400/15 text-rose-200';
  return 'bg-amber-400/15 text-amber-100';
}

async function refreshStatus() {
  backendHealthy.value = false;
  backendDetail.value = 'Verification en cours.';
  manifestError.value = '';

  const backendPromise = $fetch<{ status?: string; service?: string }>(`${apiBase}/health`, {
    cache: 'no-store',
  });
  const manifestPromise = $fetch<UpdateManifest>(updateManifestUrl, {
    cache: 'no-store',
  });

  const [backendResult, manifestResult] = await Promise.allSettled([backendPromise, manifestPromise]);

  if (backendResult.status === 'fulfilled') {
    backendHealthy.value = true;
    const serviceName = backendResult.value.service || 'backend';
    const status = backendResult.value.status || 'ok';
    backendDetail.value = `${serviceName} repond (${status}).`;
  } else {
    backendHealthy.value = false;
    backendDetail.value = 'Le backend ne repond pas pour le moment.';
  }

  if (manifestResult.status === 'fulfilled') {
    manifest.value = manifestResult.value;
  } else {
    manifest.value = null;
    manifestError.value = 'Le manifeste de release est indisponible.';
  }

  lastChecked.value = new Date().toISOString();
}

onMounted(async () => {
  const token = Cookies.get('auth_token');
  if (token) {
    try {
      const decodedToken = jwtDecode(token) as { role?: string };
      if (decodedToken.role === 'admin') {
        await router.push('/admin/users');
        return;
      }
      if (decodedToken.role === 'user') {
        await router.push('/dashboard');
        return;
      }
    } catch (error) {
      console.error('Invalid auth token:', error);
    }
  }

  await refreshStatus();
  refreshTimer.value = window.setInterval(refreshStatus, refreshSeconds * 1000);
});

onUnmounted(() => {
  if (refreshTimer.value) {
    window.clearInterval(refreshTimer.value);
  }
});
</script>
