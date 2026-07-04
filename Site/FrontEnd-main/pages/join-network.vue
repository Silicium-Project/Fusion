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

    <div class="absolute inset-0 z-0 overflow-hidden">
      <div class="absolute -top-48 left-[55%] h-[560px] w-[560px] rounded-full bg-purple-600/20 blur-3xl"></div>
      <div class="absolute top-[42%] -left-40 h-[520px] w-[520px] rounded-full bg-blue-600/15 blur-3xl"></div>
    </div>

    <main class="relative z-10 mx-auto max-w-7xl px-6 pb-20 pt-32">
      <section class="grid items-center gap-10 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <NuxtLink to="/" class="mb-8 inline-flex items-center text-white/60 hover:text-white">
            <img src="~assets/icons/Back.svg" alt="" class="mr-2 h-5 w-5" />
            Retour a l'accueil
          </NuxtLink>
          <p class="mb-4 text-sm font-bold uppercase tracking-[0.35em] text-blue-300/80">Silicium Node</p>
          <h1 class="max-w-4xl text-5xl font-extrabold leading-tight md:text-7xl">
            Rejoindre le
            <span class="bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">reseau</span>
          </h1>
          <p class="mt-6 max-w-3xl text-xl leading-8 text-white/70">
            Installez un node Silicium pour mettre votre machine a disposition du reseau. Votre PC peut calculer des fragments, verifier des resultats, puis gagner en reputation au fil des taches.
          </p>
          <div class="mt-8 flex flex-col gap-4 sm:flex-row">
            <a href="#beta-install" class="inline-flex h-14 items-center justify-center rounded-full bg-gradient-to-r from-purple-400 to-blue-400 px-8 text-lg font-bold shadow-lg shadow-purple-500/20 transition hover:from-purple-500 hover:to-blue-500">
              Installer la beta
            </a>
            <a href="#roles" class="inline-flex h-14 items-center justify-center rounded-full border border-white/20 px-8 text-lg font-bold text-white/80 transition hover:border-white/40 hover:text-white">
              Choisir un role
            </a>
          </div>
        </div>

        <section class="rounded-3xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-purple-500/10 backdrop-blur">
          <div class="rounded-2xl bg-black/30 p-5">
            <div class="mb-5 flex items-center justify-between">
              <div>
                <p class="text-sm uppercase tracking-[0.25em] text-white/40">Orchestrateur public</p>
                <p class="mt-1 font-mono text-sm text-blue-200">{{ orchestratorUrl }}</p>
              </div>
              <span class="rounded-full bg-green-500/15 px-3 py-1 text-sm font-bold text-green-200">public</span>
            </div>
            <div class="grid gap-3">
              <div v-for="item in networkChecks" :key="item.label" class="flex items-center justify-between rounded-xl bg-white/[0.04] px-4 py-3">
                <span class="text-white/70">{{ item.label }}</span>
                <span class="font-semibold" :class="item.className">{{ item.value }}</span>
              </div>
            </div>
          </div>
        </section>
      </section>

      <section id="roles" class="mt-16 grid gap-6 lg:grid-cols-3">
        <article v-for="role in roles" :key="role.title" class="rounded-2xl border border-white/10 bg-[#1f2029]/90 p-6">
          <div class="mb-5 flex h-12 w-12 items-center justify-center rounded-xl" :class="role.iconClass">
            <img :src="role.icon" alt="" class="h-6 w-6" />
          </div>
          <h2 class="text-2xl font-bold">{{ role.title }}</h2>
          <p class="mt-3 min-h-20 text-white/60">{{ role.description }}</p>
          <ul class="mt-6 space-y-3 text-sm text-white/70">
            <li v-for="point in role.points" :key="point" class="flex gap-3">
              <span class="mt-1 h-2 w-2 rounded-full bg-blue-300"></span>
              <span>{{ point }}</span>
            </li>
          </ul>
        </article>
      </section>

      <section id="beta-install" class="mt-16 grid gap-8 lg:grid-cols-[0.9fr_1.1fr]">
        <div class="rounded-2xl border border-white/10 bg-[#1f2029]/90 p-6">
          <h2 class="text-3xl font-bold">App bureau</h2>
          <p class="mt-4 text-white/65">
            La premiere application Silicium Node permettra de demarrer ou arreter le node, choisir les roles, suivre les taches et lire les logs depuis une interface simple.
          </p>
          <button disabled class="mt-6 h-12 w-full cursor-not-allowed rounded-xl bg-white/10 font-bold text-white/40">
            Telechargement bientot disponible
          </button>
          <p class="mt-4 text-sm text-white/40">
            En attendant le package desktop, l'installation beta se fait avec le repo et les scripts reseau.
          </p>
        </div>

        <div class="rounded-2xl border border-white/10 bg-black/35 p-6">
          <div class="mb-4 flex items-center justify-between gap-4">
            <div>
              <h2 class="text-2xl font-bold">Installation beta Windows</h2>
              <p class="text-white/50">Commandes temporaires pour connecter un PC au reseau public.</p>
            </div>
            <span class="rounded-full bg-yellow-400/15 px-3 py-1 text-sm font-bold text-yellow-100">beta</span>
          </div>
          <pre class="overflow-x-auto rounded-xl bg-[#0c0d12] p-5 text-sm leading-7 text-blue-100"><code>git clone git@github.com:Bkrennat/eipSilicium.git
cd eipSilicium
git checkout codex-networked-reputation-demo
.\install-silicium-windows.cmd
.\Network\scripts\start-worker.cmd {{ orchestratorUrl }} YOUR_PUBLIC_OR_LAN_IP
.\Network\scripts\start-verifier.cmd {{ orchestratorUrl }} YOUR_PUBLIC_OR_LAN_IP</code></pre>
        </div>
      </section>

      <section class="mt-16 grid gap-6 md:grid-cols-2">
        <div class="rounded-2xl border border-white/10 bg-[#1f2029]/90 p-6">
          <h2 class="text-2xl font-bold">Ce qui tourne sur votre PC</h2>
          <p class="mt-3 text-white/60">
            Le node Silicium ecoute les taches, calcule ou verifie les fragments autorises, puis renvoie un resultat signe au reseau. Les fichiers temporaires restent dans l'espace local du node.
          </p>
        </div>
        <div class="rounded-2xl border border-white/10 bg-[#1f2029]/90 p-6">
          <h2 class="text-2xl font-bold">Securite en beta</h2>
          <p class="mt-3 text-white/60">
            Ne lancez la beta que sur une machine de test. Le reseau public va progressivement ajouter identite node, reputation avancee, isolation des workloads et distribution de paiements.
          </p>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import Header from '../components/Header.vue';
import ProductsIcon from '~/assets/icons/Products.svg';
import ReceiptIcon from '~/assets/icons/Receipt.svg';
import UsersIcon from '~/assets/icons/Users.svg';
import '~/assets/css/stars.css';

const router = useRouter();
const config = useRuntimeConfig();
const orchestratorUrl = config.public.orchestratorUrl;

const roles = [
  {
    title: 'Worker',
    description: 'Calcule les fragments envoyes par le reseau et publie un resultat verifiable.',
    icon: ProductsIcon,
    iconClass: 'bg-blue-500/20',
    points: ['Utilise CPU aujourd hui, GPU plus tard', 'Recoit des fragments de workloads', 'Construit sa reputation sur les succes'],
  },
  {
    title: 'Verifier',
    description: 'Controle les resultats produits par les workers avant reassemblage.',
    icon: ReceiptIcon,
    iconClass: 'bg-green-500/20',
    points: ['Verifie les hashes et preuves', 'Vote sur les fragments', 'Renforce la confiance du reseau'],
  },
  {
    title: 'Node mixte',
    description: 'Combine calcul et verification sur la meme machine pour les tests beta.',
    icon: UsersIcon,
    iconClass: 'bg-purple-500/20',
    points: ['Simple pour contribuer vite', 'Ideal pour tester le reseau', 'Configurable role par role ensuite'],
  },
];

const networkChecks = [
  { label: 'Site public', value: 'actif', className: 'text-green-200' },
  { label: 'API publique', value: 'actif', className: 'text-green-200' },
  { label: 'Reseau P2P', value: 'beta', className: 'text-yellow-100' },
  { label: 'App bureau', value: 'en preparation', className: 'text-blue-200' },
];

const stars = ref<{ id: number; size: string; style: Record<string, string> }[]>([]);
const numStars = 90;

function goToAuth() {
  router.push('/auth');
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
