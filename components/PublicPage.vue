<template>
  <div class="public-page">
    <Header />
    <main class="public-content"><slot /></main>
    <footer class="public-footer">
      <NuxtLink to="/" class="font-black text-white">Silicium</NuxtLink>
      <p>Le calcul distribué, du travail soumis au résultat.</p>
      <NuxtLink to="/contact">Contact</NuxtLink>
    </footer>
  </div>
</template>

<script setup lang="ts">
import Header from './Header.vue';
</script>
