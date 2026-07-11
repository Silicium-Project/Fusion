<template>
  <div class="relative bg-[#131419] text-white min-h-screen overflow-hidden">
    <!-- Header -->
    <Header @register="handleRegister" />

    <!-- Animated Starfield -->
    <div class="stars" aria-hidden="true">
      <div
        v-for="star in stars"
        :key="star.id"
        class="star"
        :class="star.size"
        :style="star.style"
      ></div>
    </div>

    <!-- Background Lights -->
    <div class="absolute top-0 left-0 w-full h-full overflow-hidden z-0">
      <div class="absolute top-[-10%] left-[60%] w-[600px] h-[600px] bg-purple-600 rounded-full filter blur-3xl opacity-20 animate-pulse"></div>
      <div class="absolute top-[50%] -right-1/8 w-[700px] h-[700px] bg-blue-600 rounded-full filter blur-3xl opacity-15 animate-pulse delay-2000"></div>
    </div>

    <!-- SolanaCoin -->
    <div class="absolute top-[20%] left-[5%] w-32 h-32 opacity-10 z-0">
      <img src="~assets/img/SolanaCoin.png" alt="SolanaCoin" class="w-full h-full" />
    </div>
    <!-- SolanaCoin 2 -->
    <div class="absolute top-[60%] right-[5%] w-48 h-48 opacity-10 z-0">
      <img src="~assets/img/SolanaCoin.png" alt="SolanaCoin" class="w-full h-full transform scale-x-[-1]" />
    </div>

    <!-- Main Content -->
    <main class="relative z-10 container mx-auto px-6 pt-32 pb-16 text-center">
      <h1 class="text-5xl md:text-7xl font-extrabold leading-tight mb-4">
        Bienvenue sur
        <span class="text-transparent bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text">Silicium</span>
      </h1>
      <p class="text-xl md:text-2xl text-white/70 max-w-3xl mx-auto mb-8">
        Silicium transforme les appareils du quotidien en un superordinateur mondial propulsé par Solana. Exécutez vos tâches de calcul complexes à moindre coût, ou monétisez votre puissance matérielle inutilisée en toute sécurité.
      </p>
      <button @click="handleRegister" class="flex items-center mx-auto space-x-2 px-8 py-4 text-xl font-bold rounded-full bg-gradient-to-r from-purple-400 to-blue-400 hover:from-purple-500 hover:to-blue-500 transition-all duration-300 shadow-lg hover:shadow-purple-500/50 transform hover:scale-105">
        <span>Commencer gratuitement</span>
        <img src="~assets/icons/Right.svg" alt="Right-Icon" class="w-8 h-8" />
      </button>

      <!-- Dashboard Preview -->
      <div class="mt-20 w-full max-w-6xl mx-auto group">
        <img 
          src="~/assets/img/Dashboard.png" 
          alt="Aperçu du tableau de bord"
          class="w-full h-auto rounded-2xl border-2 border-white/10 shadow-2xl shadow-purple-500/10 transition-all duration-300 group-hover:scale-105 group-hover:shadow-purple-400/30 group-hover:border-white/20"
        />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import Header from '../components/Header.vue';
import { useRouter } from 'vue-router';
import '~/assets/css/stars.css';

const router = useRouter();

function handleRegister() {
  router.push('/auth?mode=register');
}

const stars = ref([]);
const numStars = 100;

onMounted(() => {
  // Starfield Generation
  for (let i = 0; i < numStars; i++) {
    const size = Math.random() > 0.7 ? (Math.random() > 0.8 ? 'star-lg' : 'star-md') : 'star-sm';
    stars.value.push({
      id: i,
      size: size,
      style: {
        '--star-left': `${Math.random() * 100}%`,
        '--star-top': `${Math.random() * 100}%`,
        '--animation-delay': `${Math.random() * 3}s`,
      }
    });
  }
});
</script>
