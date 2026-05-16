<template>
  <div class="bg-[#131419] min-h-screen flex items-center justify-center">
    <div class="w-full max-w-md p-8 space-y-8 bg-[#1f2029] rounded-2xl shadow-lg">
      <div class="text-center">
        <h1 class="text-3xl font-extrabold text-white">
          <span class="text-transparent bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text">{{ isLogin ? 'Content de vous revoir !' : 'Créer un compte' }}</span>
        </h1>
        <p class="mt-2 text-white/50">
          {{ isLogin ? 'Connectez-vous pour continuer' : 'Inscrivez-vous pour commencer' }}
        </p>
      </div>
      <form class="space-y-6" @submit.prevent="handleSubmit">
        <div v-if="!isLogin" class="grid grid-cols-2 gap-4">
          <input v-model="form.firstName" type="text" placeholder="Prénom" required class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
          <input v-model="form.lastName" type="text" placeholder="Nom de famille" required class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
        </div>
        <input v-if="!isLogin" v-model="form.username" type="text" placeholder="Nom d'utilisateur" required class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
        <input v-model="form.email" type="email" placeholder="E-mail" required class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
        <input v-model="form.password" type="password" placeholder="Mot de passe" required class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
        <button type="submit" class="w-full h-12 rounded-lg bg-gradient-to-r from-purple-400 to-blue-400 text-white font-bold text-lg hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg">
          {{ isLogin ? 'Connexion' : 'S\'inscrire' }}
        </button>
      </form>
      <div class="text-center">
        <button @click="isLogin = !isLogin" class="text-white/50 hover:text-white">
          {{ isLogin ? 'Besoin d\'un compte ? S\'inscrire' : 'Vous avez déjà un compte ? Se connecter' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue';
import { useRouter } from '#vue-router';
import Cookies from 'js-cookie';
import { jwtDecode } from 'jwt-decode';

const isLogin = ref(true);
const router = useRouter();
const config = useRuntimeConfig();
const apiBase = config.public.apiBase;

const form = reactive({
  firstName: '',
  lastName: '',
  username: '',
  email: '',
  password: '',
});

const handleSubmit = async () => {
  if (isLogin.value) {
    await login();
  } else {
    await register();
  }
};

const login = async () => {
  try {
    const response = await $fetch(`${apiBase}/login`, {
      method: 'POST',
      body: {
        email: form.email,
        password: form.password,
      }
    });

    Cookies.set('auth_token', response.token, {
      expires: 7,
      sameSite: 'Strict',
    });

    const decodedToken = jwtDecode(response.token) as { role: string };

    if (decodedToken.role === 'user') {
      await router.push('/dashboard');
    }
  } catch (error) {
    console.error(error);
  }
};

const register = async () => {
  try {
    await $fetch(`${apiBase}/register`, {
      method: 'POST',
      body: {
        username: form.username,
        first_name: form.firstName,
        last_name: form.lastName,
        email: form.email,
        password: form.password,
        phone_number: '', // Add a phone number field if needed
      }
    });
    // switch to login mode after successful registration
    isLogin.value = true;
  } catch (error) {
    console.error(error);
  }
};
</script>
