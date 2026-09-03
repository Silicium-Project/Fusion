<template>
  <PublicPage>
    <p class="public-eyebrow">Contact</p>
    <h1 class="public-title max-w-4xl">Une question ?<br><span class="text-purple-300">Parlons de Silicium.</span></h1>
    <p class="public-lead">Une difficulté sur le site, un retour d’expérience ou une idée pour le projet ? Retrouvez ici les informations utiles pour échanger avec l’équipe.</p>
    <div class="mt-12 grid gap-6 md:grid-cols-2">
      <section class="public-card">
        <h2 class="text-2xl font-bold">Écrire à l’équipe</h2>
        <template v-if="contactEmail">
          <p>Votre messagerie s’ouvrira pour rédiger votre message. Aucun envoi n’est effectué automatiquement.</p>
          <a :href="`mailto:${contactEmail}`" class="public-button public-button-primary mt-6 break-all">{{ contactEmail }}</a>
        </template>
        <p v-else>Les coordonnées de contact seront publiées ici prochainement. Aucun formulaire d’envoi n’est encore disponible.</p>
      </section>
      <section class="public-card">
        <h2 class="text-2xl font-bold">Un problème technique ?</h2>
        <p>Commencez par vérifier l’état des services. Pour décrire un problème, notez la page concernée, les étapes pour le reproduire et le message d’erreur affiché.</p>
        <NuxtLink to="/service" class="public-button mt-6">Vérifier les services</NuxtLink>
      </section>
    </div>
    <aside class="mt-8 border-l-2 border-purple-400 pl-6 text-slate-300 leading-7">Ne partagez jamais votre mot de passe, votre token de connexion ou la phrase de récupération de votre portefeuille.</aside>
  </PublicPage>
</template>

<script setup lang="ts">
import PublicPage from '../components/PublicPage.vue';
const contactEmail = useRuntimeConfig().public.contactEmail;
useSeoMeta({ title: 'Contact — Silicium', description: 'Questions, retours et problèmes techniques : retrouvez les informations de contact du projet Silicium.' });
</script>
