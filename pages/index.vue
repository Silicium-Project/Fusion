<template>
  <div class="bg-[#131419] text-white min-h-screen">
    <!-- Header -->
    <Header @register="handleRegister" />

    <!-- Background Lights -->
    <div class="absolute top-0 left-0 w-full h-full overflow-hidden z-0">
      <div class="absolute top-[-5%] left-[70%] w-[500px] h-[500px] bg-purple-500 rounded-full filter blur-3xl opacity-20 animate-pulse"></div>
      <div class="absolute top-[60%] -right-1/8 w-[500px] h-[500px] bg-blue-500 rounded-full filter blur-3xl opacity-20 animate-pulse delay-2000"></div>
    </div>

    <!-- EtherCoin -->
    <div class="absolute top-[20%] left-[5%] w-32 h-32 opacity-10 z-0">
      <img src="~assets/img/EtherCoin.png" alt="EtherCoin" class="w-full h-full" />
    </div>
    <!-- EtherCoin 2 -->
    <div class="absolute top-[60%] right-[5%] w-48 h-48 opacity-10 z-0">
      <img src="~assets/img/EtherCoin.png" alt="EtherCoin" class="w-full h-full transform scale-x-[-1]" />
    </div>


    <!-- Main Content -->
    <main class="relative z-10 container mx-auto px-6 pt-32 pb-16 text-center">
      <h1 class="text-5xl md:text-7xl font-extrabold leading-tight mb-4">
        Bienvenue sur
        <span class="text-transparent bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text">Silicium</span>
      </h1>
      <p class="text-xl md:text-2xl text-white/70 max-w-3xl mx-auto mb-8">
        La plateforme ultime pour gérer vos projets, équipes et clients avec une efficacité inégalée.
      </p>
      <button @click="handleRegister" class="flex items-center mx-auto space-x-2 px-8 py-4 text-xl font-bold rounded-full bg-gradient-to-r from-purple-400 to-blue-400 hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg">
        <span>Commencer gratuitement</span>
        <img src="~assets/icons/Right.svg" alt="Right-Icon" class="w-8 h-8" />
      </button>

      <!-- Dashboard Preview Placeholder -->
      <div class="mt-20 w-full max-w-6xl mx-auto h-96 bg-black/20 rounded-2xl border-2 border-white/10 flex items-center justify-center">
        <p class="text-white/50 text-2xl">Aperçu du tableau de bord</p>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import Header from '../components/Header.vue'
import { onMounted } from 'vue';
import { useRouter } from 'vue-router';
import Cookies from "js-cookie";
import {jwtDecode} from "jwt-decode";

function handleRegister() {
  router.push(`/auth`);
}

const router = useRouter();

onMounted(() => {
  const token = Cookies.get('auth_token')

  if (token) {
    try {
      const decodedToken = jwtDecode(token) as { role: string };

      if (decodedToken.role === 'admin') {
        router.push('/admin/users');
      } else if (decodedToken.role === 'user') {
        router.push('/dashboard');
      }
    } catch (e) {
      console.error('Error decoding token:', e);
    }
    }
});
</script>
