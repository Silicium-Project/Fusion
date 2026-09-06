<template>
  <main class="auth-page">
    <section class="auth-page__story">
      <span class="eyebrow">Espace Silicium</span><h1>La maîtrise de vos calculs, <em>sans le bruit.</em></h1><p>Soumettez une charge, suivez sa distribution et retrouvez le résultat avec ses preuves depuis un environnement unique.</p>
      <div class="auth-page__flow"><div v-for="item in story" :key="item.title"><span><UiIcon :name="item.icon"/></span><strong>{{ item.title }}</strong><small>{{ item.text }}</small></div></div>
    </section>
    <section class="auth-card surface">
      <NuxtLink to="/" class="auth-card__back"><UiIcon name="arrow"/>Retour à l’accueil</NuxtLink>
      <div class="auth-card__heading"><span class="eyebrow">{{ isLogin ? 'Bon retour' : 'Bienvenue' }}</span><h2>{{ isLogin ? 'Connectez-vous' : 'Créez votre espace' }}</h2><p>{{ isLogin ? 'Retrouvez vos tâches et votre réseau.' : 'Quelques informations suffisent pour démarrer.' }}</p></div>
      <div class="auth-card__modes" role="tablist" aria-label="Mode d’authentification"><button type="button" :class="{ active: isLogin }" @click="setMode('login')">Connexion</button><button type="button" :class="{ active: !isLogin }" @click="setMode('register')">Inscription</button></div>
      <form class="auth-form" :aria-busy="submitting" @submit.prevent="submit">
        <div v-if="!isLogin" class="auth-form__names"><label class="field"><span>Prénom</span><input v-model.trim="form.firstName" class="input" autocomplete="given-name" required placeholder="Prénom"></label><label class="field"><span>Nom</span><input v-model.trim="form.lastName" class="input" autocomplete="family-name" required placeholder="Nom de famille"></label></div>
        <label v-if="!isLogin" class="field"><span>Nom d’utilisateur</span><input v-model.trim="form.username" class="input" autocomplete="username" required placeholder="Nom d'utilisateur"></label>
        <label class="field"><span>{{ isLogin ? 'E-mail ou nom d’utilisateur' : 'Adresse e-mail' }}</span><input v-if="isLogin" v-model.trim="form.identifier" class="input" autocomplete="username" required placeholder="E-mail ou nom d’utilisateur"><input v-else v-model.trim="form.email" class="input" type="email" autocomplete="email" required placeholder="vous@exemple.fr"></label>
        <label class="field"><span>Mot de passe</span><input v-model="form.password" class="input" type="password" :autocomplete="isLogin ? 'current-password' : 'new-password'" minlength="8" required placeholder="8 caractères minimum"></label>
        <UiNotice v-if="error" tone="danger">{{ error }}</UiNotice><UiNotice v-if="success" tone="success">{{ success }}</UiNotice>
        <UiButton type="submit" size="large" icon="arrow" :loading="submitting">{{ isLogin ? 'Se connecter' : 'Créer mon compte' }}</UiButton>
      </form>
      <p class="auth-card__legal">En continuant, vous accédez à l’environnement expérimental Silicium.</p>
    </section>
  </main>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'auth', middleware: 'guest' });
const route = useRoute();
const router = useRouter();
const session = useSession();
const isLogin = computed(() => route.query.mode !== 'register');
const submitting = ref(false);
const error = ref('');
const success = ref('');
const form = reactive({ firstName: '', lastName: '', username: '', email: '', identifier: '', password: '' });
const story = [{ title: 'Soumettre', text: 'Une entrée et des paramètres explicites.', icon: 'upload' }, { title: 'Observer', text: 'Une distribution lisible en direct.', icon: 'network' }, { title: 'Vérifier', text: 'Un résultat relié à ses preuves.', icon: 'shield' }];
async function setMode(mode: 'login' | 'register') { error.value = ''; success.value = ''; form.password = ''; await router.replace({ path: '/auth', query: { ...route.query, mode } }); }
async function submit() {
  if (submitting.value) return;
  error.value = ''; success.value = ''; submitting.value = true;
  try {
    if (isLogin.value) {
      await session.login(form.identifier, form.password);
      const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/dashboard';
      await router.push(redirect);
    } else {
      if (new TextEncoder().encode(form.password).length > 72) throw Object.assign(new Error(), { data: { message: 'Le mot de passe dépasse la limite de 72 octets.' } });
      await session.register({ email: form.email.trim(), password: form.password, username: form.username.trim(), first_name: form.firstName.trim(), last_name: form.lastName.trim() });
      form.identifier = form.email.trim();
      await setMode('login');
      success.value = 'Compte créé. Vous pouvez maintenant vous connecter.';
    }
  } catch (failure) { error.value = session.errorMessage(failure); }
  finally { submitting.value = false; }
}
useSeoMeta({ title: () => `${isLogin.value ? 'Connexion' : 'Inscription'} — Silicium`, description: 'Accédez à votre espace de calcul distribué Silicium.' });
</script>

<style scoped>
.auth-page{position:relative;z-index:1;display:grid;min-height:100vh;grid-template-columns:1fr minmax(440px,.78fr);align-items:center;gap:clamp(3rem,8vw,8rem);width:min(calc(100% - 4rem),1180px);margin:auto;padding:6rem 0 3rem}.auth-page__story{max-width:580px}.auth-page__story h1{margin:1rem 0 0;font-size:clamp(3.2rem,5.5vw,5.5rem);line-height:.94;letter-spacing:-.07em}.auth-page__story h1 em{color:var(--ink-400);font-style:normal;font-weight:600}.auth-page__story>p{max-width:510px;margin:1.5rem 0 0;color:var(--ink-600);font-size:.86rem;line-height:1.8}.auth-page__flow{display:grid;grid-template-columns:repeat(3,1fr);gap:.7rem;margin-top:2.7rem}.auth-page__flow>div{padding:1rem;border:1px solid var(--border);border-radius:var(--radius-md);background:rgba(255,255,255,.55)}.auth-page__flow span{display:grid;width:2.2rem;height:2.2rem;place-items:center;border-radius:.65rem;background:var(--mint-100);color:var(--mint-700)}.auth-page__flow>div:nth-child(3) span{background:var(--violet-100);color:var(--violet-600)}.auth-page__flow svg{width:.9rem}.auth-page__flow strong,.auth-page__flow small{display:block}.auth-page__flow strong{margin-top:1rem;font-size:.68rem}.auth-page__flow small{margin-top:.25rem;color:var(--ink-500);font-size:.56rem;line-height:1.45}
.auth-card{padding:1.6rem}.auth-card__back{display:inline-flex;align-items:center;gap:.45rem;color:var(--ink-500);font-size:.64rem;font-weight:700}.auth-card__back svg{width:.8rem;transform:rotate(180deg)}.auth-card__heading{margin-top:2.2rem}.auth-card__heading h2{margin:.55rem 0 0;font-size:2rem;letter-spacing:-.05em}.auth-card__heading p{margin:.5rem 0 0;color:var(--ink-500);font-size:.7rem}.auth-card__modes{display:grid;grid-template-columns:1fr 1fr;gap:.25rem;margin-top:1.5rem;padding:.25rem;border-radius:.72rem;background:var(--ink-100)}.auth-card__modes button{height:2.35rem;border:0;border-radius:.55rem;background:transparent;color:var(--ink-500);cursor:pointer;font-size:.68rem;font-weight:750}.auth-card__modes button.active{background:white;color:var(--ink-950);box-shadow:var(--shadow-sm)}.auth-form{display:grid;gap:1rem;margin-top:1.3rem}.auth-form__names{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}.auth-form :deep(.ui-button){width:100%;margin-top:.25rem}.auth-card__legal{margin:1.2rem 0 0;color:var(--ink-400);font-size:.56rem;text-align:center}
@media(max-width:900px){.auth-page{grid-template-columns:1fr;width:min(calc(100% - 2rem),500px);padding-top:7rem}.auth-page__story{display:none}}@media(max-width:500px){.auth-page{width:calc(100% - 1.25rem);padding-bottom:1rem}.auth-card{padding:1.2rem}.auth-form__names{grid-template-columns:1fr}}
</style>
