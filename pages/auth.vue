<template>
  <div class="bg-[#131419] min-h-screen flex items-center justify-center">
    <div class="w-full max-w-md p-8 space-y-8 bg-[#1f2029] rounded-2xl shadow-lg">
      <NuxtLink to="/" class="inline-flex items-center gap-2 text-white/60 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-purple-400 rounded">
        <span aria-hidden="true">←</span>
        Retour à l’accueil
      </NuxtLink>
      <div class="text-center">
        <h1 class="text-3xl font-extrabold text-white">
          <span class="text-transparent bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text">{{ isLogin ? 'Content de vous revoir !' : 'Créer un compte' }}</span>
        </h1>
        <p class="mt-2 text-white/50">
          {{ isLogin ? 'Connectez-vous pour continuer' : 'Inscrivez-vous pour commencer' }}
        </p>
      </div>
      <p v-if="errorMessage" role="alert" class="text-red-300">{{ errorMessage }}</p>
      <p v-if="successMessage" role="status" class="text-green-300">{{ successMessage }}</p>
      <form class="space-y-6" :aria-busy="isSubmitting" @submit.prevent="handleSubmit">
        <div v-if="!isLogin" class="grid grid-cols-2 gap-4">
          <input v-model="form.firstName" type="text" placeholder="Prénom" required :disabled="isSubmitting" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
          <input v-model="form.lastName" type="text" placeholder="Nom de famille" required :disabled="isSubmitting" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
        </div>
        <input v-if="!isLogin" v-model="form.username" type="text" placeholder="Nom d'utilisateur" required :disabled="isSubmitting" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
        <input v-if="isLogin" v-model="form.identifier" type="text" placeholder="E-mail ou nom d’utilisateur" aria-label="E-mail ou nom d’utilisateur" autocomplete="username" required :disabled="isSubmitting" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
        <input v-else v-model="form.email" type="email" placeholder="E-mail" aria-label="E-mail" autocomplete="email" required :disabled="isSubmitting" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
        <input v-model="form.password" type="password" placeholder="Mot de passe" required :disabled="isSubmitting" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
        <button type="submit" :disabled="isSubmitting" class="w-full h-12 rounded-lg bg-gradient-to-r from-purple-400 to-blue-400 text-white font-bold text-lg hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg">
          {{ isSubmitting ? 'Veuillez patienter…' : (isLogin ? 'Connexion' : 'S\'inscrire') }}
        </button>
      </form>
      <div class="text-center">
        <button :disabled="isSubmitting" @click="switchMode(!isLogin)" class="text-white/50 hover:text-white">
          {{ isLogin ? 'Besoin d\'un compte ? S\'inscrire' : 'Vous avez déjà un compte ? Se connecter' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Cookies from 'js-cookie';
import { authErrorMessage, tokenExpiry } from '../utils/auth';

const route = useRoute();
const router = useRouter();
const apiBase = useRuntimeConfig().public.apiBase;
const isLogin = computed(() => route.query.mode !== 'register');
const isSubmitting = ref(false);
const errorMessage = ref('');
const successMessage = ref('');
const form = reactive({ firstName: '', lastName: '', username: '', email: '', identifier: '', password: '' });

async function switchMode(login: boolean) {
  errorMessage.value = '';
  successMessage.value = '';
  form.password = '';
  await router.replace({ path: '/auth', query: { mode: login ? 'login' : 'register' } });
}

async function handleSubmit() {
  if (isSubmitting.value) return;
  isSubmitting.value = true;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    if (isLogin.value) await login();
    else await register();
  } catch (error) {
    errorMessage.value = authErrorMessage(error);
  } finally {
    isSubmitting.value = false;
  }
}

async function login() {
  const response = await $fetch<{ token: string }>(`${apiBase}/login`, {
    method: 'POST', retry: 0, timeout: 15_000,
    body: { identifier: form.identifier.trim(), password: form.password },
  });
  const expires = tokenExpiry(response.token);
  if (!expires) throw new Error('Invalid login response');
  Cookies.set('auth_token', response.token, {
    expires, path: '/', sameSite: 'Strict', secure: window.location.protocol === 'https:',
  });
  await router.push('/');
}

async function register() {
  if (new TextEncoder().encode(form.password).length > 72) {
    errorMessage.value = 'Le mot de passe dépasse la limite de 72 octets.';
    return;
  }
  await $fetch(`${apiBase}/register`, {
    method: 'POST', retry: 0, timeout: 15_000,
    body: {
      email: form.email.trim(), password: form.password, username: form.username.trim(),
      first_name: form.firstName.trim(), last_name: form.lastName.trim(),
    },
  });
  form.identifier = form.email.trim();
  await switchMode(true);
  successMessage.value = 'Compte créé ! Vous pouvez maintenant vous connecter.';
}
</script>
