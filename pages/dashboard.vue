<template>
  <div class="bg-[#131419] text-white min-h-screen flex">
    <!-- Vertical Navbar -->
    <nav class="w-64 bg-[#1f2029] p-6 flex flex-col">
      <h1 class="text-3xl font-extrabold text-white mb-10">
        <span class="text-transparent bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text">Silicium</span>
      </h1>
      <ul class="space-y-4">
        <li>
          <a href="#" class="flex items-center text-lg text-white/80 hover:text-white">
            <img src="~assets/icons/Users.svg" alt="Users-Icon" class="w-6 h-6 mr-4" />
            Tableau de bord
          </a>
        </li>
        <li>
          <a href="#" class="flex items-center text-lg text-white/80 hover:text-white">
            <img src="~assets/icons/Products.svg" alt="Products-Icon" class="w-6 h-6 mr-4" />
            Mes appareils
          </a>
        </li>
        <li>
          <a href="#" class="flex items-center text-lg text-white/80 hover:text-white">
            <img src="~assets/icons/Receipt.svg" alt="Receipt-Icon" class="w-6 h-6 mr-4" />
            Calculs
          </a>
        </li>
        <li>
          <a href="#" class="flex items-center text-lg text-white/80 hover:text-white">
            <img src="~assets/icons/Transactions.svg" alt="Transactions-Icon" class="w-6 h-6 mr-4" />
            Transactions
          </a>
        </li>
        <li>
          <a href="#" class="flex items-center text-lg text-white/80 hover:text-white">
            <span class="w-6 h-6 mr-4"></span> <!-- Icon Placeholder -->
            Impact écologique
          </a>
        </li>
        <li>
          <a href="#" class="flex items-center text-lg text-white/80 hover:text-white">
            <img src="~assets/icons/Users.svg" alt="Users-Icon" class="w-6 h-6 mr-4" />
            Communauté
          </a>
        </li>
      </ul>
      <div class="mt-auto">
        <a href="#" class="flex items-center text-lg text-white/80 hover:text-white">
          <span class="w-6 h-6 mr-4"></span> <!-- Icon Placeholder -->
          Paramètre
        </a>
      </div>
    </nav>

    <!-- Main Content -->
    <main class="flex-1 p-10">
      <h2 class="text-4xl font-bold mb-2">Tableau de bord</h2>
      <p class="text-lg text-white/50 mb-10">Bienvenue dans Silicium, votre plateforme de calcul distribué</p>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        <!-- Card 1 -->
        <div class="bg-[#1f2029] rounded-2xl p-6 flex items-center">
          <div class="w-12 h-12 bg-purple-500/20 rounded-lg flex items-center justify-center mr-6">
            <img src="~assets/icons/Users.svg" alt="Users-Icon" class="w-6 h-6" />
          </div>
          <div>
            <p class="text-white/50">Utilisateurs</p>
            <p class="text-2xl font-bold">1,234</p>
          </div>
        </div>
        <!-- Card 2 -->
        <div class="bg-[#1f2029] rounded-2xl p-6 flex items-center">
          <div class="w-12 h-12 bg-blue-500/20 rounded-lg flex items-center justify-center mr-6">
            <img src="~assets/icons/Products.svg" alt="Products-Icon" class="w-6 h-6" />
          </div>
          <div>
            <p class="text-white/50">Appareils connectés</p>
            <p class="text-2xl font-bold">56</p>
          </div>
        </div>
        <!-- Card 3 -->
        <div class="bg-[#1f2029] rounded-2xl p-6 flex items-center">
          <div class="w-12 h-12 bg-green-500/20 rounded-lg flex items-center justify-center mr-6">
            <img src="~assets/icons/Receipt.svg" alt="Receipt-Icon" class="w-6 h-6" />
          </div>
          <div>
            <p class="text-white/50">Calculs en cours</p>
            <p class="text-2xl font-bold">12</p>
          </div>
        </div>
        <!-- Card 4 -->
        <div class="bg-[#1f2029] rounded-2xl p-6 flex items-center">
          <div class="w-12 h-12 bg-yellow-500/20 rounded-lg flex items-center justify-center mr-6">
            <img src="~assets/icons/Transactions.svg" alt="Transactions-Icon" class="w-6 h-6" />
          </div>
          <div>
            <p class="text-white/50">Transactions</p>
            <p class="text-2xl font-bold">4,567</p>
          </div>
        </div>
        <!-- Card 5 -->
        <div class="bg-[#1f2029] rounded-2xl p-6 flex items-center">
          <div class="w-12 h-12 bg-red-500/20 rounded-lg flex items-center justify-center mr-6">
            <!-- Icon Placeholder -->
          </div>
          <div>
            <p class="text-white/50">Impact CO2 économisé</p>
            <p class="text-2xl font-bold">2.5 T</p>
          </div>
        </div>
        <!-- Card 6 -->
        <div class="bg-[#1f2029] rounded-2xl p-6 flex items-center">
          <div class="w-12 h-12 bg-indigo-500/20 rounded-lg flex items-center justify-center mr-6">
            <img src="~assets/icons/Users.svg" alt="Users-Icon" class="w-6 h-6" />
          </div>
          <div>
            <p class="text-white/50">Membres de la communauté</p>
            <p class="text-2xl font-bold">890</p>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
</script>
