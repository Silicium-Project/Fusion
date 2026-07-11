<template>
  <div class="relative min-h-screen overflow-hidden bg-[#131419] text-white">
    <Header @register="goToAuth" />

    <div class="stars" aria-hidden="true">
      <div
        v-for="star in stars"
        :key="star.id"
        class="star"
        :class="star.size"
        :style="star.style"
      ></div>
    </div>

    <main class="relative z-10 mx-auto max-w-6xl px-6 pb-20 pt-32">
      <NuxtLink to="/" class="mb-8 inline-flex items-center text-white/60 hover:text-white">
        <img src="~assets/icons/Back.svg" alt="" class="mr-2 h-5 w-5" />
        Retour a l'accueil
      </NuxtLink>

      <section class="grid items-center gap-10 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <p class="mb-4 text-sm font-bold uppercase tracking-[0.35em] text-blue-300/80">Silicium Node</p>
          <h1 class="max-w-4xl text-5xl font-extrabold leading-tight md:text-7xl">
            Votre PC peut rejoindre
            <span class="bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">le reseau</span>
          </h1>
          <p class="mt-6 max-w-3xl text-xl leading-8 text-white/70">
            Installez l'app, cliquez sur Activer mon PC, puis Silicium utilise automatiquement votre machine quand une tache compatible est disponible.
          </p>

          <div class="mt-8 flex flex-col gap-4 sm:flex-row">
            <a :href="nodeAppWindowsUrl" download class="inline-flex h-14 items-center justify-center rounded-full bg-gradient-to-r from-purple-400 to-blue-400 px-8 text-lg font-bold shadow-lg shadow-purple-500/20 transition hover:from-purple-500 hover:to-blue-500">
              Telecharger l'app Windows
            </a>
            <a href="#details" class="inline-flex h-14 items-center justify-center rounded-full border border-white/20 px-8 text-lg font-bold text-white/80 transition hover:border-white/40 hover:text-white">
              En savoir plus
            </a>
          </div>
        </div>

        <section class="rounded-3xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-purple-500/10 backdrop-blur">
          <div class="rounded-2xl bg-black/30 p-5">
            <p class="text-sm uppercase tracking-[0.25em] text-white/40">Etat du reseau</p>
            <div class="mt-5 grid gap-4">
              <div class="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
                <span class="text-white/55">PC connectes</span>
                <strong class="mt-2 block text-5xl">{{ connectedNodesLabel }}</strong>
                <p class="mt-2 text-sm text-white/50">{{ networkStatusLabel }}</p>
              </div>
              <div class="grid gap-3 sm:grid-cols-2">
                <div class="rounded-xl bg-white/[0.04] px-4 py-3">
                  <span class="block text-sm text-white/45">Orchestrateur</span>
                  <strong :class="networkStatus?.ok ? 'text-green-200' : 'text-yellow-100'">
                    {{ networkStatus?.ok ? 'en ligne' : 'verification...' }}
                  </strong>
                </div>
                <div class="rounded-xl bg-white/[0.04] px-4 py-3">
                  <span class="block text-sm text-white/45">App bureau</span>
                  <strong class="text-blue-200">Windows</strong>
                </div>
              </div>
            </div>
          </div>
        </section>
      </section>

      <section id="details" class="mt-16 grid gap-6 md:grid-cols-3">
        <article v-for="item in steps" :key="item.title" class="rounded-2xl border border-white/10 bg-[#1f2029]/90 p-6">
          <h2 class="text-2xl font-bold">{{ item.title }}</h2>
          <p class="mt-3 text-white/60">{{ item.description }}</p>
        </article>
      </section>

      <section class="mt-16 rounded-2xl border border-white/10 bg-[#1f2029]/90 p-6">
        <div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 class="text-3xl font-bold">Une app, un bouton</h2>
            <p class="mt-3 max-w-3xl text-white/60">
              L'app affiche le statut du PC, les travaux effectues, l'historique et les gains confirmes. Le retrait du reseau reste possible a tout moment.
            </p>
          </div>
          <a :href="nodeAppWindowsUrl" download class="inline-flex h-12 items-center justify-center rounded-xl bg-gradient-to-r from-purple-400 to-blue-400 px-6 font-bold text-white transition hover:from-purple-500 hover:to-blue-500">
            Telecharger
          </a>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import Header from '../components/Header.vue';
import '~/assets/css/stars.css';

const router = useRouter();
const config = useRuntimeConfig();
const nodeAppWindowsUrl = config.public.nodeAppWindowsUrl;

const { data: networkStatus } = await useFetch<{
  ok: boolean;
  connectedNodes: number | null;
  orchestratorUrl: string;
  updatedAt: string;
}>('/api/network-status', {
  default: () => ({ ok: false, connectedNodes: null, orchestratorUrl: '', updatedAt: '' }),
});

const connectedNodesLabel = computed(() => {
  const count = networkStatus.value?.connectedNodes;
  return typeof count === 'number' ? String(count) : '-';
});

const networkStatusLabel = computed(() => {
  if (!networkStatus.value?.ok) {
    return "L'orchestrateur est en cours de verification.";
  }
  const count = networkStatus.value.connectedNodes;
  if (!count || count <= 1) {
    return "Le reseau public est pret et attend d'autres PC.";
  }
  return `${count} machine(s) visibles par l'orchestrateur.`;
});

const steps = [
  {
    title: '1. Installer',
    description: "L'app prepare ce qu'il faut pour faire tourner un node Silicium sur votre PC.",
  },
  {
    title: '2. Activer',
    description: 'Votre machine rejoint le reseau et attend une tache adaptee a sa reputation et sa disponibilite.',
  },
  {
    title: '3. Suivre',
    description: "Le dashboard local affiche le statut, les travaux termines, l'historique et les gains.",
  },
];

const stars = ref<{ id: number; size: string; style: Record<string, string> }[]>([]);
const numStars = 70;

function goToAuth() {
  router.push('/auth?mode=register');
}

onMounted(() => {
  for (let i = 0; i < numStars; i++) {
    const size = Math.random() > 0.7 ? (Math.random() > 0.8 ? 'star-lg' : 'star-md') : 'star-sm';
    stars.value.push({
      id: i,
      size,
      style: {
        '--star-left': `${Math.random() * 100}%`,
        '--star-top': `${Math.random() * 100}%`,
        '--animation-delay': `${Math.random() * 3}s`,
      },
    });
  }
});
</script>
