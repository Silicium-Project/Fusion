<template>
  <div class="bg-[#131419] text-white min-h-screen flex">
    <!-- Vertical Navbar -->
    <nav class="w-64 bg-[#1f2029] p-6 flex flex-col">
      <h1 class="text-3xl font-extrabold text-white mb-10">
        <span class="text-transparent bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text">Silicium</span>
      </h1>
      <ul class="space-y-4">
        <li>
          <a href="#" class="flex items-center text-lg text-white/80 hover:text-white hover-gradient-underline">
            <img src="~assets/icons/Users.svg" alt="Users-Icon" class="w-6 h-6 mr-4" />
            Tableau de bord
          </a>
        </li>
        <li>
          <a href="#" class="flex items-center text-lg text-white/80 hover:text-white hover-gradient-underline">
            <img src="~assets/icons/Products.svg" alt="Products-Icon" class="w-6 h-6 mr-4" />
            Mes appareils
          </a>
        </li>
        <li>
          <a href="#" class="flex items-center text-lg text-white/80 hover:text-white hover-gradient-underline">
            <img src="~assets/icons/Receipt.svg" alt="Receipt-Icon" class="w-6 h-6 mr-4" />
            Calculs
          </a>
        </li>
        <li>
          <a href="#" class="flex items-center text-lg text-white/80 hover:text-white hover-gradient-underline">
            <img src="~assets/icons/Transactions.svg" alt="Transactions-Icon" class="w-6 h-6 mr-4" />
            Transactions
          </a>
        </li>
        <li>
          <a href="#" class="flex items-center text-lg text-white/80 hover:text-white hover-gradient-underline">
            <span class="w-6 h-6 mr-4"></span> <!-- Icon Placeholder -->
            Impact écologique
          </a>
        </li>
        <li>
          <a href="#" class="flex items-center text-lg text-white/80 hover:text-white hover-gradient-underline">
            <img src="~assets/icons/Users.svg" alt="Users-Icon" class="w-6 h-6 mr-4" />
            Communauté
          </a>
        </li>
      </ul>
    </nav>

    <!-- Main Content -->
    <main class="flex-1 p-10 relative">
      <!-- Profile section -->
      <div class="absolute top-10 right-10">
        <NuxtLink to="/profile" class="flex items-center space-x-3">
          <div class="w-10 h-10 rounded-full bg-gradient-to-r from-purple-400 to-blue-400 flex items-center justify-center font-bold text-xl">
            {{ user ? (user.username || user.email)?.[0].toUpperCase() : '' }}
          </div>
          <span class="text-white font-semibold">{{ user?.username || user?.email }}</span>
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

      <!-- Soumettre une tâche Button -->
      <button @click="isModalOpen = true" class="fixed bottom-10 right-10 bg-gradient-to-r from-purple-400 to-blue-400 text-white font-bold py-3 px-6 rounded-full shadow-lg transform hover:scale-105 transition-transform">
        Soumettre une tâche
      </button>

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

const isModalOpen = ref(false);
const user = ref(null);
const config = useRuntimeConfig();
const apiBase = config.public.apiBase;

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
    } catch (error) {
      console.error("Failed to fetch user data:", error);
      // Handle error, e.g., by redirecting to login
    }
  }
});
</script>
