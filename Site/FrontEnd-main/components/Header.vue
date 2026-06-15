<template>
  <header class="fixed top-0 left-0 w-full bg-transparent flex items-center justify-between p-6 z-50">
    <!-- Left side: Title and Buttons -->
    <div class="flex items-center space-x-4">
      <!-- Title (Silicium) -->
      <span class="text-white font-extrabold text-xl">
        Silicium
      </span>

      <!-- A propos Button -->
      <button class="flex items-center space-x-2 px-6 py-3 text-xl font-normal text-white bg-transparent transition-all hover-gradient-underline">
        <span>A propos</span>
      </button>

      <!-- Service Button -->
      <button class="flex items-center space-x-2 px-6 py-3 text-xl font-normal text-white bg-transparent transition-all hover-gradient-underline">
        <span>Service</span>
      </button>

      <!-- Contact Button -->
      <button class="flex items-center space-x-2 px-6 py-3 text-xl font-normal text-white bg-transparent transition-all hover-gradient-underline">
        <span>Contact</span>
      </button>
    </div>

    <!-- Right side: Sign In and Sign Up Buttons -->
    <div class="flex items-center space-x-4 ml-auto">
      <!-- Se connecter Button -->
      <button @click="handleSignIn" class="flex items-center space-x-2 px-6 py-3 text-xl font-bold rounded-full border-2 border-white hover:border-transparent hover:border-gradient-to-br hover:from-purple-400 hover:to-blue-400 bg-transparent hover:bg-gradient-to-r transition-all shadow-lg text-white transform hover:scale-105">
        <span>Se connecter</span>
      </button>

      <!-- S'inscrire Button -->
      <button @click="handleSignIn" class="flex items-center space-x-2 px-6 py-3 text-xl font-bold rounded-full bg-gradient-to-br from-purple-400 to-blue-400 hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg transform hover:scale-105">
        <span>S'inscrire</span>
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">


const emits = defineEmits(["register"]);

const handleSignIn = () => {
  emits("register");
};
</script>
