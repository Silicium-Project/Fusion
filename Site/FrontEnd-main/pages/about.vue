<template>
  <div class="relative min-h-screen overflow-hidden bg-[#131419] text-white">
    <Header />

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

      <section class="grid gap-10 lg:grid-cols-[1fr_0.8fr]">
        <div>
          <p class="mb-4 text-sm font-bold uppercase tracking-[0.35em] text-blue-300/80">A propos</p>
          <h1 class="max-w-4xl text-5xl font-extrabold leading-tight md:text-7xl">
            Un reseau de calcul
            <span class="bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">distribue</span>
          </h1>
          <p class="mt-6 max-w-3xl text-xl leading-8 text-white/70">
            Silicium connecte des machines volontaires pour executer, verifier et tracer des taches de calcul. Le reseau P2P transporte les donnees utiles, tandis que Solana garde une trace transparente des etapes importantes.
          </p>
        </div>

        <div class="rounded-3xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-purple-500/10">
          <h2 class="text-2xl font-bold">Objectif</h2>
          <p class="mt-4 text-white/65">
            Rendre accessible une puissance de calcul partagee pour du rendu, de la video, du calcul scientifique ou d'autres workloads generiques.
          </p>
        </div>
      </section>

      <section class="mt-16 grid gap-6 md:grid-cols-3">
        <article v-for="item in pillars" :key="item.title" class="rounded-2xl border border-white/10 bg-[#1f2029]/90 p-6">
          <h2 class="text-2xl font-bold">{{ item.title }}</h2>
          <p class="mt-3 text-white/60">{{ item.description }}</p>
        </article>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import Header from '../components/Header.vue';
import '~/assets/css/stars.css';

const pillars = [
  {
    title: 'Calcul',
    description: 'Les taches sont fragmentees puis attribuees aux machines disponibles selon leur capacite et leur reputation.',
  },
  {
    title: 'Verification',
    description: 'Des verificateurs independants controlent les resultats avant le reassemblage final.',
  },
  {
    title: 'Transparence',
    description: 'Le layer Solana trace les actions importantes sans transporter les donnees lourdes.',
  },
];

const stars = ref<{ id: number; size: string; style: Record<string, string> }[]>([]);

onMounted(() => {
  for (let i = 0; i < 70; i++) {
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
