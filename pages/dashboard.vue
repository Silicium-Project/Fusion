<template>
  <div class="bg-[#131419] text-white min-h-screen flex">
    <!-- Vertical Navbar -->
    <nav class="w-64 bg-[#1f2029] p-4 flex flex-col justify-between rounded-tr-2xl rounded-br-2xl border-r border-black/20">
      <div>
        <div class="p-4 mb-4">
          <h1 class="text-3xl font-extrabold text-white">
            <span class="text-transparent bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text">Silicium</span>
          </h1>
        </div>
        <ul class="space-y-2">
          <li>
            <a href="#" class="flex items-center text-lg text-white font-semibold p-3 rounded-xl bg-gradient-to-r from-purple-500/20 to-blue-500/20">
              <img src="~assets/icons/Users.svg" alt="Dashboard-Icon" class="w-6 h-6 mr-4" />
              Tableau de bord
            </a>
          </li>
          <li>
            <a href="#" class="flex items-center text-lg text-white/60 hover:text-white hover:bg-black/20 p-3 rounded-xl transition-colors duration-200">
              <img src="~assets/icons/Products.svg" alt="Devices-Icon" class="w-6 h-6 mr-4" />
              Mes appareils
            </a>
          </li>
          <li>
            <a href="#" class="flex items-center text-lg text-white/60 hover:text-white hover:bg-black/20 p-3 rounded-xl transition-colors duration-200">
              <img src="~assets/icons/Receipt.svg" alt="Calculations-Icon" class="w-6 h-6 mr-4" />
              Calculs
            </a>
          </li>
          <li>
            <a href="#" class="flex items-center text-lg text-white/60 hover:text-white hover:bg-black/20 p-3 rounded-xl transition-colors duration-200">
              <img src="~assets/icons/Transactions.svg" alt="Transactions-Icon" class="w-6 h-6 mr-4" />
              Transactions
            </a>
          </li>
          <li>
            <a href="#" class="flex items-center text-lg text-white/60 hover:text-white hover:bg-black/20 p-3 rounded-xl transition-colors duration-200">
              <img src="~assets/icons/Users.svg" alt="Community-Icon" class="w-6 h-6 mr-4" />
              Communauté
            </a>
          </li>
        </ul>
      </div>
      <div class="p-4">
        <button @click="isModalOpen = true" class="w-full h-12 rounded-xl bg-gradient-to-r from-purple-400 to-blue-400 text-white font-bold text-lg hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg transform hover:scale-105">
          Soumettre une tâche
        </button>
      </div>
    </nav>

    <!-- Main Content -->
    <main class="flex-1 p-10 relative select-none">
      <!-- Profile section -->
      <div class="absolute top-10 right-10 bg-black/20 rounded-lg p-2 flex items-center space-x-4">
        <div v-if="solBalance !== null" class="text-white font-semibold pl-2">
          {{ solBalance.toFixed(4) }} SOL
        </div>
        <span v-if="solBalance !== null" class="text-white/30">|</span>
        <NuxtLink to="/profile" class="flex items-center space-x-3">
          <div class="w-10 h-10 rounded-full bg-gradient-to-r from-purple-400 to-blue-400 flex items-center justify-center font-bold text-xl">
            {{ user ? (user.username || user.email)?.[0].toUpperCase() : '' }}
          </div>
          <span class="text-white font-semibold pr-2">{{ user?.username || user?.email }}</span>
        </NuxtLink>
      </div>

      <h2 class="text-4xl font-bold mb-2">Tableau de bord</h2>
      <p class="text-lg text-white/50 mb-10">Bienvenue dans Silicium, votre plateforme de calcul distribué</p>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        <!-- Card 1 -->
        <div class="bg-[#1f2029] rounded-2xl p-6 flex items-center transition-all duration-300 transform hover:scale-105 border-2 border-transparent hover:border-purple-400">
          <div class="w-12 h-12 bg-purple-500/20 rounded-lg flex items-center justify-center mr-6">
            <img src="~assets/icons/Users.svg" alt="Users-Icon" class="w-6 h-6" />
          </div>
          <div>
            <p class="text-white/50">Utilisateurs</p>
            <p class="text-2xl font-bold">1,234</p>
          </div>
        </div>
        <!-- Card 2 -->
        <div class="bg-[#1f2029] rounded-2xl p-6 flex items-center transition-all duration-300 transform hover:scale-105 border-2 border-transparent hover:border-blue-400">
          <div class="w-12 h-12 bg-blue-500/20 rounded-lg flex items-center justify-center mr-6">
            <img src="~assets/icons/Products.svg" alt="Products-Icon" class="w-6 h-6" />
          </div>
          <div>
            <p class="text-white/50">Appareils connectés</p>
            <p class="text-2xl font-bold">56</p>
          </div>
        </div>
        <!-- Card 3 -->
        <div class="bg-[#1f2029] rounded-2xl p-6 flex items-center transition-all duration-300 transform hover:scale-105 border-2 border-transparent hover:border-green-400">
          <div class="w-12 h-12 bg-green-500/20 rounded-lg flex items-center justify-center mr-6">
            <img src="~assets/icons/Receipt.svg" alt="Receipt-Icon" class="w-6 h-6" />
          </div>
          <div>
            <p class="text-white/50">Calculs en cours</p>
            <p class="text-2xl font-bold">12</p>
          </div>
        </div>
        <!-- Card 4 -->
        <div class="bg-[#1f2029] rounded-2xl p-6 flex items-center transition-all duration-300 transform hover:scale-105 border-2 border-transparent hover:border-yellow-400">
          <div class="w-12 h-12 bg-yellow-500/20 rounded-lg flex items-center justify-center mr-6">
            <img src="~assets/icons/Transactions.svg" alt="Transactions-Icon" class="w-6 h-6" />
          </div>
          <div>
            <p class="text-white/50">Transactions</p>
            <p class="text-2xl font-bold">4,567</p>
          </div>
        </div>
        <!-- Card 5 -->
        <div class="bg-[#1f2029] rounded-2xl p-6 flex items-center transition-all duration-300 transform hover:scale-105 border-2 border-transparent hover:border-red-400">
          <div class="w-12 h-12 bg-red-500/20 rounded-lg flex items-center justify-center mr-6">
            <!-- Icon Placeholder -->
          </div>
          <div>
            <p class="text-white/50">Impact CO2 économisé</p>
            <p class="text-2xl font-bold">2.5 T</p>
          </div>
        </div>
        <!-- Card 6 -->
        <div class="bg-[#1f2029] rounded-2xl p-6 flex items-center transition-all duration-300 transform hover:scale-105 border-2 border-transparent hover:border-indigo-400">
          <div class="w-12 h-12 bg-indigo-500/20 rounded-lg flex items-center justify-center mr-6">
            <img src="~assets/icons/Users.svg" alt="Users-Icon" class="w-6 h-6" />
          </div>
          <div>
            <p class="text-white/50">Membres de la communauté</p>
            <p class="text-2xl font-bold">890</p>
          </div>
        </div>
      </div>

      <!-- Charts Section -->
      <div class="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div class="bg-[#1f2029] rounded-2xl p-6">
          <highcharts :options="userGrowthOptions" />
        </div>
        <div class="bg-[#1f2029] rounded-2xl p-6">
          <highcharts :options="deviceTypesOptions" />
        </div>
      </div>

      <!-- Modal -->
      <div v-if="isModalOpen" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 transition-opacity duration-300" :class="isModalOpen ? 'opacity-100' : 'opacity-0'">
        <div class="bg-[#1f2029] rounded-2xl p-8 w-full max-w-lg transform transition-all duration-300" :class="isModalOpen ? 'scale-100' : 'scale-95'">
          <div class="flex justify-between items-center mb-6">
            <h3 class="text-2xl font-bold">Information de la tâche</h3>
            <button @click="isModalOpen = false" class="text-white/50 hover:text-white">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>
          <form>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
              <input type="text" placeholder="Type de tâche" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
              <input type="text" placeholder="Priorité" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
            </div>
            <input type="text" placeholder="Nom de la tâche" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400 mb-6">
            <textarea placeholder="Description" class="w-full h-24 bg-black/20 rounded-lg px-4 py-2 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400 mb-6"></textarea>
            <div class="mb-6">
              <label for="file-input" class="block text-white/50 mb-2">Fichier d'entrée</label>
              <input id="file-input" type="file" class="w-full text-white">
            </div>
            <button type="submit" class="w-full h-12 rounded-lg bg-gradient-to-r from-purple-400 to-blue-400 text-white font-bold text-lg hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg">
              Envoyer
            </button>
          </form>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import Cookies from 'js-cookie';
import * as web3 from '@solana/web3.js';

const isModalOpen = ref(false);
const user = ref(null);
const solBalance = ref(null);
const config = useRuntimeConfig();
const apiBase = config.public.apiBase;

const userGrowthOptions = ref({
  chart: { type: 'line', backgroundColor: 'transparent' },
  title: { text: 'Evolution des utilisateurs', style: { color: '#ffffff' } },
  xAxis: { categories: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'], labels: { style: { color: '#ffffff' } } },
  yAxis: { title: { text: 'Nombre d\'utilisateurs', style: { color: '#ffffff' } }, labels: { style: { color: '#ffffff' } } },
  series: [{ name: 'Utilisateurs', data: [120, 250, 400, 580, 800, 1050], color: '#8b5cf6' }],
  legend: { itemStyle: { color: '#ffffff' } },
});

const deviceTypesOptions = ref({
  chart: { type: 'pie', backgroundColor: 'transparent' },
  title: { text: 'Types d\'appareils connectés', style: { color: '#ffffff' } },
  tooltip: { pointFormat: '{series.name}: <b>{point.percentage:.1f}%</b>' },
  plotOptions: {
    pie: {
      allowPointSelect: true,
      cursor: 'pointer',
      dataLabels: { enabled: true, format: '<b>{point.name}</b>: {point.percentage:.1f} %', style: { color: 'white' } }
    }
  },
  series: [{
    name: 'Types',
    colorByPoint: true,
    data: [
      { name: 'CPU', y: 70, color: '#8b5cf6' },
      { name: 'GPU', y: 20, color: '#3b82f6' },
      { name: 'ASIC', y: 10, color: '#10b981' }
    ]
  }],
  legend: { itemStyle: { color: '#ffffff' } },
});

onMounted(async () => {
  const token = Cookies.get('auth_token');
  if (token) {
    try {
      const fetchedUser = await $fetch(`${apiBase}/user`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      user.value = fetchedUser;

      if (fetchedUser.walletAddress) {
        const connection = new web3.Connection(web3.clusterApiUrl('devnet'));
        const publicKey = new web3.PublicKey(fetchedUser.walletAddress);
        const balance = await connection.getBalance(publicKey);
        solBalance.value = balance / web3.LAMPORTS_PER_SOL;
      }

    } catch (error) {
      console.error("Failed to fetch user data:", error);
      // Handle error, e.g., by redirecting to login
    }
  }
});
</script>
