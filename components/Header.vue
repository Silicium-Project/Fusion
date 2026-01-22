<template>
  <header class="fixed top-0 left-0 w-full bg-transparent flex items-center justify-between p-6 z-50">
    <!-- Left side: Title and Buttons -->
    <div class="flex items-center space-x-4">
      <!-- Title (Silicium) -->
      <span class="text-white font-extrabold text-xl">
        Silicium
      </span>

      <!-- Accueil Button -->
      <button class="flex items-center space-x-2 px-6 py-3 text-xl font-normal text-white bg-transparent hover:underline transition-all">
        <span>Accueil</span>
      </button>

      <!-- Pricing Button -->
      <button class="flex items-center space-x-2 px-6 py-3 text-xl font-normal text-white bg-transparent hover:underline transition-all">
        <span>Service</span>
      </button>
    </div>

    <!-- Right side: Sign In and Sign Up Buttons -->
    <div class="flex items-center space-x-4 ml-auto">
      <!-- Sign In Button -->
      <button @click="handleSignIn" class="flex items-center space-x-2 px-6 py-3 text-xl font-bold rounded-full border-2 border-white hover:border-transparent hover:border-gradient-to-br hover:from-purple-400 hover:to-blue-400 bg-transparent hover:bg-gradient-to-r transition-all shadow-lg text-white">
        <span>Sign In</span>
      </button>

      <!-- Sign Up Button -->
      <button @click="handleSignIn" class="flex items-center space-x-2 px-6 py-3 text-xl font-bold rounded-full bg-gradient-to-br from-purple-400 to-blue-400 hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg">
        <span>Sign Up</span>
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
