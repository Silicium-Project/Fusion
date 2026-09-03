<template>
  <PublicPage>
    <p class="public-eyebrow">À propos de Silicium</p>
    <h1 class="public-title max-w-4xl">Relier les machines.<br><span class="text-purple-300">Faire avancer les calculs.</span></h1>
    <p class="public-lead">Silicium est un projet de calcul distribué : un site pour soumettre des travaux, un backend pour les orchestrer et un réseau de nœuds pour les exécuter.</p>
    <section class="public-section grid gap-10 md:grid-cols-2">
      <div><p class="public-eyebrow">L’idée</p><h2 class="mt-4">Un point d’entrée.<br>Une exécution distribuée.</h2></div>
      <div class="space-y-5 text-lg leading-8 text-slate-300">
        <p>Le projet cherche à rendre un réseau de calcul accessible depuis une interface commune. Vous définissez votre travail ; Silicium permet de le soumettre, d’en suivre l’exécution et d’en récupérer le résultat.</p>
        <p>Le raytracing constitue un premier cas d’usage : un rendu peut être divisé en parcelles, puis traité par les machines du réseau.</p>
      </div>
    </section>
    <section class="public-section">
      <h2>Les trois briques du projet</h2>
      <div class="mt-8 grid gap-5 md:grid-cols-3">
        <article class="public-card"><p class="public-eyebrow !mt-0">01 · Le site</p><h3 class="mt-4">Soumettre et suivre</h3><p>Le compte utilisateur et le dashboard rassemblent la soumission des tâches, leurs statuts et leurs résultats.</p></article>
        <article class="public-card"><p class="public-eyebrow !mt-0">02 · Le backend</p><h3 class="mt-4">Orchestrer</h3><p>L’API fait le lien entre le site et le réseau pour prendre en charge les travaux et exposer leur progression.</p></article>
        <article class="public-card"><p class="public-eyebrow !mt-0">03 · Le réseau</p><h3 class="mt-4">Exécuter et observer</h3><p>Les nœuds participent au calcul distribué. Un dashboard d’observation et une intégration Solana Devnet accompagnent le projet.</p></article>
      </div>
    </section>
    <section class="public-section public-card">
      <p class="public-eyebrow !mt-0">Un projet en développement</p>
      <h2 class="mt-4">Construire, tester, améliorer.</h2>
      <p>Silicium évolue encore. Le Devnet est un environnement de test ; les disponibilités des services et des versions se consultent sur la page Service.</p>
      <div class="mt-6 flex flex-wrap gap-3"><NuxtLink to="/service" class="public-button">Voir les services</NuxtLink><NuxtLink to="/contact" class="public-button">Nous contacter</NuxtLink></div>
    </section>
  </PublicPage>
</template>

<script setup lang="ts">
import PublicPage from '../components/PublicPage.vue';
useSeoMeta({ title: 'À propos — Silicium', description: 'Découvrez le projet Silicium, son réseau de calcul distribué et son premier cas d’usage : le raytracing.' });
</script>
