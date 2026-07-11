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

    <main class="relative z-10 mx-auto max-w-5xl px-6 pb-20 pt-32">
      <NuxtLink to="/" class="mb-8 inline-flex items-center text-white/60 hover:text-white">
        <img src="~assets/icons/Back.svg" alt="" class="mr-2 h-5 w-5" />
        Retour a l'accueil
      </NuxtLink>

      <section class="rounded-3xl border border-white/10 bg-[#1f2029]/90 p-8 shadow-2xl shadow-purple-500/10">
        <p class="mb-4 text-sm font-bold uppercase tracking-[0.35em] text-blue-300/80">Contact</p>
        <h1 class="text-5xl font-extrabold leading-tight md:text-6xl">
          Parlons de
          <span class="bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">Silicium</span>
        </h1>
        <p class="mt-5 max-w-3xl text-xl leading-8 text-white/65">
          Une question sur le reseau, l'app bureau, les workloads ou une future integration ? Envoyez un message a l'equipe.
        </p>

        <div class="mt-8 grid gap-4 md:grid-cols-2">
          <a href="mailto:contact@silicium.network" class="rounded-2xl border border-white/10 bg-white/[0.04] p-5 transition hover:border-blue-300/50">
            <span class="block text-sm uppercase tracking-[0.25em] text-white/40">Email</span>
            <strong class="mt-2 block text-xl">contact@silicium.network</strong>
          </a>
          <NuxtLink to="/join-network" class="rounded-2xl border border-white/10 bg-white/[0.04] p-5 transition hover:border-purple-300/50">
            <span class="block text-sm uppercase tracking-[0.25em] text-white/40">Participer</span>
            <strong class="mt-2 block text-xl">Rejoindre le reseau</strong>
          </NuxtLink>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import Header from '../components/Header.vue';
import '~/assets/css/stars.css';

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
