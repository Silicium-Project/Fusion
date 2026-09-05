<template>
  <div class="auth-shell min-h-screen text-white">
    <div class="auth-grid" aria-hidden="true"></div>

    <NuxtLink to="/" class="absolute left-5 top-5 z-20 flex items-center gap-3 sm:left-8 sm:top-8" aria-label="Retour à l’accueil">
      <span class="brand-mark" aria-hidden="true"><span></span><span></span><span></span><span></span></span>
      <span class="font-extrabold tracking-[-0.03em]">Silicium</span>
    </NuxtLink>

    <main class="relative z-10 grid min-h-screen lg:grid-cols-[0.92fr_1.08fr]">
      <section class="hidden border-r border-white/[0.07] p-12 lg:flex lg:flex-col lg:justify-end xl:p-16">
        <div class="max-w-xl">
          <p class="text-xs font-bold uppercase tracking-[0.2em] text-[#9f94ff]">Espace Silicium</p>
          <h1 class="mt-5 text-5xl font-extrabold leading-[1.02] tracking-[-0.055em] xl:text-6xl">
            Pilotez toute votre puissance de calcul.
          </h1>
          <p class="mt-6 max-w-lg text-base leading-7 text-white/45">
            Soumettez vos tâches, observez le réseau et récupérez les résultats depuis un environnement unique.
          </p>
          <div class="mt-10 grid grid-cols-3 gap-3">
            <div v-for="item in highlights" :key="item.label" class="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-4">
              <span class="font-mono text-lg font-semibold text-white/80">{{ item.value }}</span>
              <p class="mt-1 text-[11px] text-white/30">{{ item.label }}</p>
            </div>
          </div>
        </div>
      </section>

      <section class="flex items-center justify-center px-5 py-28 sm:px-8 lg:py-16">
        <div class="w-full max-w-[450px]">
          <div class="mb-8">
            <p class="text-xs font-bold uppercase tracking-[0.18em] text-[#8ef3df]">{{ isLogin ? 'Bon retour' : 'Bienvenue' }}</p>
            <h2 class="mt-3 text-3xl font-extrabold tracking-[-0.04em] sm:text-4xl">{{ isLogin ? 'Connectez-vous' : 'Créez votre espace' }}</h2>
            <p class="mt-3 text-sm leading-6 text-white/42">{{ isLogin ? 'Retrouvez vos tâches et l’état de votre réseau.' : 'Quelques informations suffisent pour démarrer.' }}</p>
          </div>

          <div class="mb-7 grid grid-cols-2 rounded-xl border border-white/[0.07] bg-white/[0.025] p-1">
            <button type="button" class="mode-button" :class="isLogin ? 'mode-button-active' : ''" @click="setMode(true)">Connexion</button>
            <button type="button" class="mode-button" :class="!isLogin ? 'mode-button-active' : ''" @click="setMode(false)">Inscription</button>
          </div>

          <form class="space-y-4" :aria-busy="isSubmitting" @submit.prevent="handleSubmit">
            <div v-if="!isLogin" class="grid grid-cols-2 gap-3">
              <label class="field-label">Prénom<input v-model.trim="form.firstName" type="text" autocomplete="given-name" required :disabled="isSubmitting" class="field-input" placeholder="Prénom"></label>
              <label class="field-label">Nom<input v-model.trim="form.lastName" type="text" autocomplete="family-name" required :disabled="isSubmitting" class="field-input" placeholder="Nom de famille"></label>
            </div>
            <label v-if="!isLogin" class="field-label">Nom d’utilisateur<input v-model.trim="form.username" type="text" autocomplete="username" required :disabled="isSubmitting" class="field-input" placeholder="Nom d'utilisateur"></label>
            <label v-if="isLogin" class="field-label">E-mail ou nom d’utilisateur<input v-model.trim="form.identifier" type="text" autocomplete="username" required :disabled="isSubmitting" class="field-input" placeholder="E-mail ou nom d’utilisateur"></label>
            <label v-else class="field-label">Adresse e-mail<input v-model.trim="form.email" type="email" autocomplete="email" required :disabled="isSubmitting" class="field-input" placeholder="E-mail"></label>
            <label class="field-label">Mot de passe<input v-model="form.password" type="password" :autocomplete="isLogin ? 'current-password' : 'new-password'" minlength="8" required :disabled="isSubmitting" class="field-input" placeholder="Mot de passe"></label>

            <p v-if="errorMessage" role="alert" class="rounded-xl border border-rose-400/15 bg-rose-400/[0.07] px-4 py-3 text-sm text-rose-200">{{ errorMessage }}</p>
            <p v-if="successMessage" role="status" class="rounded-xl border border-emerald-400/15 bg-emerald-400/[0.07] px-4 py-3 text-sm text-emerald-200">{{ successMessage }}</p>

            <button type="submit" :disabled="isSubmitting" class="submit-button group">
              <span>{{ isSubmitting ? 'Veuillez patienter…' : isLogin ? 'Se connecter' : 'Créer mon compte' }}</span>
              <svg v-if="!isSubmitting" viewBox="0 0 20 20" class="h-4 w-4 transition-transform group-hover:translate-x-0.5" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 10h14m-5-5 5 5-5 5" stroke-linecap="round" stroke-linejoin="round" /></svg>
            </button>
          </form>

          <p class="mt-7 text-center text-xs text-white/28">
            En continuant, vous accédez à l’environnement de calcul Silicium.
          </p>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import Cookies from 'js-cookie';
import { authErrorMessage, tokenExpiry } from '../utils/auth';

const route = useRoute();
const router = useRouter();
const config = useRuntimeConfig();
const apiBase = config.public.apiBase;
const isLogin = computed(() => route.query.mode !== 'register');
const isSubmitting = ref(false);
const errorMessage = ref('');
const successMessage = ref('');
const highlights = [
  { value: '01', label: 'Interface unifiée' },
  { value: 'Live', label: 'Suivi du réseau' },
  { value: 'Auto', label: 'Distribution' },
];
const form = reactive({ firstName: '', lastName: '', username: '', email: '', identifier: '', password: '' });

async function setMode(loginMode: boolean) {
  errorMessage.value = '';
  successMessage.value = '';
  form.password = '';
  await router.replace({ path: '/auth', query: { mode: loginMode ? 'login' : 'register' } });
}

async function handleSubmit() {
  if (isSubmitting.value) return;
  errorMessage.value = '';
  successMessage.value = '';
  isSubmitting.value = true;
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
    method: 'POST',
    retry: 0,
    timeout: 15_000,
    body: { username: form.username.trim(), first_name: form.firstName.trim(), last_name: form.lastName.trim(), email: form.email.trim(), password: form.password },
  });
  form.identifier = form.email.trim();
  await setMode(true);
  successMessage.value = 'Compte créé ! Vous pouvez maintenant vous connecter.';
}

useSeoMeta({ title: () => `${isLogin.value ? 'Connexion' : 'Inscription'} — Silicium` });
</script>

<style scoped>
.auth-shell { position: relative; overflow: hidden; background: radial-gradient(circle at 18% 82%, rgba(125, 104, 255, .14), transparent 30%), radial-gradient(circle at 86% 20%, rgba(94, 234, 212, .07), transparent 27%), #080a0f; }
.auth-grid { position: absolute; inset: 0; opacity: .28; background-image: linear-gradient(rgba(255,255,255,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.03) 1px,transparent 1px); background-size: 56px 56px; mask-image: linear-gradient(110deg, black, transparent 78%); }
.brand-mark { display:grid;width:2rem;height:2rem;grid-template-columns:repeat(2,.48rem);grid-template-rows:repeat(2,.48rem);place-content:center;gap:.2rem;border:1px solid rgba(255,255,255,.16);border-radius:.7rem;background:linear-gradient(145deg,rgba(145,128,255,.3),rgba(94,234,212,.08)); }.brand-mark span{border-radius:.12rem;background:#a89cff}.brand-mark span:nth-child(2),.brand-mark span:nth-child(3){background:#67e8d4}
.mode-button { border-radius: .55rem; padding: .7rem; font-size: .8rem; font-weight: 700; color: rgba(255,255,255,.35); transition: background-color 160ms ease,color 160ms ease,box-shadow 160ms ease; }.mode-button-active { background: rgba(255,255,255,.08); color: white; box-shadow: 0 5px 18px rgba(0,0,0,.18); }
.field-label { display: block; color: rgba(255,255,255,.48); font-size: .72rem; font-weight: 650; }.field-input { display:block;width:100%;height:3.25rem;margin-top:.5rem;border:1px solid rgba(255,255,255,.085);border-radius:.8rem;background:rgba(255,255,255,.03);padding:0 .95rem;color:white;font-size:.875rem;transition:border-color 160ms ease,background-color 160ms ease,box-shadow 160ms ease }.field-input::placeholder{color:rgba(255,255,255,.18)}.field-input:focus{border-color:rgba(155,140,255,.6);background:rgba(255,255,255,.045);box-shadow:0 0 0 3px rgba(155,140,255,.1);outline:none}
.submit-button { display:flex;width:100%;height:3.35rem;align-items:center;justify-content:center;gap:.65rem;border-radius:.85rem;background:#f4f5f7;color:#080a0f;font-size:.875rem;font-weight:800;transition:background-color 160ms ease,transform 160ms ease }.submit-button:hover:not(:disabled){background:#d9ff9d;transform:translateY(-1px)}
</style>
