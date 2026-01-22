<template>
  <div class="bg-[#131419]">
    <!-- Header -->
    <Header @register="handleRegister" />

    <!-- Main Content -->
    <div class="relative text-white min-h-screen pt-20">
      <!-- EtherCoin -->
      <div class="absolute top-[30%] left-[45%] transform -translate-x-1/2 -translate-y-1/2 opacity-100 z-0">
        <img src="~assets/img/EtherCoin.png" alt="EtherCoin" class="max-w-[10%] md:max-w-[10%]" />
      </div>
      <!-- EtherCoin 2 -->
      <div class="absolute top-[40%] left-[87%] transform -translate-x-1/2 -translate-y-1/2 opacity-100 z-0">
        <img src="~assets/img/EtherCoin.png" alt="EtherCoin" class="max-w-[110%] md:max-w-[110%] transform scale-x-[-1]" />
      </div>
      <!-- EtherCoin 3 -->
      <div class="absolute top-[0%] left-[65%] transform -translate-x-1/2 -translate-y-1/2 opacity-100 z-0">
        <img src="~assets/img/EtherCoin.png" alt="EtherCoin" class="max-w-[200%] md:max-w-[60%]" />
      </div>

      <!-- Centered Text -->
      <div class="text-center font-extrabold text-5xl md:text-5xl sm:text-4xl mt-32 sm:mt-40 md:mt-52 mx-auto max-w-md md:max-w-7xl relative z-10">
        <p>
          Integer ut justo<br />
          <span class="text-transparent bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text">tristique</span>
          , tempus nulla ut,  <span class="text-transparent bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text">tincidunt justo</span>.
        </p>
      </div>

      <!-- Description Text -->
      <div class="text-center font-semibold text-xl md:text-2xl sm:text-base opacity-70 mt-8 mx-auto max-w-7xl relative z-10">
        <p>*
          Lorem ipsum dolor sit amet, consectetur adipiscing elit.<br />
          Nullam scelerisque elit nec pulvinar tempus.
        </p>
      </div>

      <!-- Gradient Button -->
      <div class="flex justify-center mt-10 relative z-10">
        <button @click="handleRegister" class="flex items-center space-x-2 px-6 py-3 text-xl font-medium rounded-full bg-gradient-to-r from-purple-400 to-blue-400 hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg">
          <span>Start for free</span>
          <img src="~assets/icons/Right.svg" alt="Right-Icon" class="w-8 h-8" />
        </button>
      </div>

      <!-- Additional Text -->
      <div class="text-center font-semibold text-lg md:text-base sm:text-base opacity-70 mt-2 mx-auto max-w-7xl relative z-10">
        <p>
          No Subscriptions needed
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Header from '../components/Header.vue'
import { onMounted } from 'vue';
import { useRouter } from 'vue-router';
import Cookies from "js-cookie";
import {jwtDecode} from "jwt-decode";

function handleRegister() {
  router.push(`/register`);
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
