<template>
  <PublicPage>
    <section class="grid gap-12 lg:grid-cols-[1.25fr_1fr] lg:items-center">
      <div>
        <p class="public-eyebrow">Silicium · Calcul distribué</p>
        <h1 class="public-title">Un projet.<br>Plusieurs machines.<br><span class="text-purple-300">Un même calcul.</span></h1>
        <p class="public-lead">Soumettez un travail, répartissez son exécution sur le réseau et retrouvez vos résultats au même endroit. Silicium relie votre projet à une infrastructure de calcul distribuée.</p>
        <div class="mt-8 flex flex-wrap gap-3">
          <NuxtLink to="/dashboard" class="public-button public-button-primary">Accéder au dashboard <span aria-hidden="true">↗</span></NuxtLink>
          <NuxtLink to="/about" class="public-button">Découvrir le projet</NuxtLink>
        </div>
        <p class="mt-5 text-sm text-slate-400">Projet en développement · Environnement Solana Devnet</p>
      </div>
      <aside class="public-card !p-8" aria-label="Parcours d’un calcul Silicium">
        <div class="flex items-center justify-between border-b border-white/10 pb-6">
          <p class="public-eyebrow">Du fichier au résultat</p>
          <span class="text-sm text-slate-400">01 — 03</span>
        </div>
        <ol class="mt-2">
          <li v-for="(step, index) in steps" :key="step.title" class="flex gap-5 border-b border-white/10 py-6 last:border-0 last:pb-0">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-purple-400/10 text-sm font-bold text-purple-300">{{ index + 1 }}</span>
            <div><h2 class="text-xl font-bold">{{ step.title }}</h2><p class="!mt-2 text-sm">{{ step.description }}</p></div>
          </li>
        </ol>
      </aside>
    </section>
    <section class="public-section">
      <p class="public-eyebrow">Un parcours, de bout en bout</p>
      <h2 class="mt-4">Concentrez-vous sur votre travail.<br>Gardez la main sur son exécution.</h2>
      <div class="mt-8 grid gap-5 md:grid-cols-3">
        <article v-for="feature in features" :key="feature.title" class="public-card">
          <h3>{{ feature.title }}</h3><p>{{ feature.description }}</p>
        </article>
      </div>
    </section>
    <section class="public-section flex flex-wrap items-center justify-between gap-8 border-y border-white/10 py-10">
      <div><p class="public-eyebrow">Côté infrastructure</p><h2 class="mt-4">Les services, en toute visibilité.</h2><p class="public-lead !mt-3">État de l’API, application Windows et canaux de mise à jour.</p></div>
      <NuxtLink to="/service" class="public-button">Consulter les services <span aria-hidden="true">→</span></NuxtLink>
    </section>
  </PublicPage>
</template>

<script setup lang="ts">
import PublicPage from '../components/PublicPage.vue';

useSeoMeta({
  title: 'Silicium — Le calcul distribué, simplement',
  description: 'Soumettez vos calculs, suivez leur exécution sur le réseau Silicium et récupérez vos résultats depuis un même espace.',
});

const steps = [
  { title: 'Soumettre', description: 'Un fichier de configuration, une priorité et une durée maximale définissent votre travail.' },
  { title: 'Distribuer', description: 'Le backend orchestre l’exécution du travail sur les nœuds du réseau Silicium.' },
  { title: 'Récupérer', description: 'Le dashboard permet de suivre les tâches et de télécharger les résultats disponibles.' },
];
const features = [
  { title: 'Un espace de pilotage', description: 'Retrouvez vos tâches, leur statut et leurs résultats dans votre dashboard.' },
  { title: 'Un premier usage : le raytracing', description: 'Soumettez une scène et configurez le nombre de parcelles pour son rendu distribué.' },
  { title: 'Un réseau observable', description: 'Consultez les tâches réseau et accédez au dashboard d’observation du Devnet.' },
];
</script>
