<template>
  <main class="auth-page marketing-page">
    <section v-reveal="'left'" class="auth-story">
      <span class="marketing-kicker">Votre espace Silicium</span>
      <h1 class="marketing-title">Vos projets,<br><em>au même endroit.</em></h1>
      <p class="marketing-lede">Silicium s’occupe du travail en arrière-plan. Vous retrouvez ici vos projets et leurs résultats.</p>
      <ol class="auth-story__steps"><li v-for="(item,index) in story" :key="item.title"><span>{{ String(index + 1).padStart(2,'0') }}</span><div><strong>{{ item.title }}</strong><small>{{ item.text }}</small></div><UiIcon :name="item.icon" /></li></ol>
    </section>
    <section v-reveal="'right'" class="auth-card marketing-glass">
      <NuxtLink to="/" class="auth-card__back"><UiIcon name="arrow" />Retour à l’accueil</NuxtLink>
      <div class="auth-card__heading"><span class="marketing-kicker">{{ isLogin ? 'Retrouver vos projets' : 'Rejoindre Silicium' }}</span><h2>{{ isLogin ? 'Connectez-vous' : 'Créez votre espace' }}</h2><p>{{ isLogin ? 'Vos projets et leurs résultats vous attendent.' : 'Un compte suffit pour suivre vos projets et récupérer leurs résultats.' }}</p></div>
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
const story = [{ title: 'Envoyer', text: 'Transmettez votre projet en un seul geste.', icon: 'upload' }, { title: 'Calculer', text: 'Le réseau répartit le travail entre ses machines.', icon: 'network' }, { title: 'Récupérer', text: 'Retrouvez un résultat contrôlé et compréhensible.', icon: 'shield' }];
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
.auth-page{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(28rem,.72fr);align-items:center;gap:clamp(2.5rem,6vw,6rem);width:min(calc(100% - 3rem),1240px);min-height:100vh;margin:auto;padding:5rem 0 3rem}.auth-story{min-width:0;max-width:700px}.auth-story .marketing-title{max-width:640px;font-size:clamp(3rem,4.9vw,5.4rem)}.auth-story__steps{display:grid;max-width:580px;gap:.65rem;margin:2.2rem 0 0;padding:0;list-style:none}.auth-story__steps li{display:grid;grid-template-columns:2rem 1fr auto;align-items:center;gap:.8rem;padding:.7rem 0;border-top:1px solid var(--border)}.auth-story__steps li:last-child{border-bottom:1px solid var(--border)}.auth-story__steps>li>span{color:var(--ink-400);font-family:var(--font-mono);font-size:.58rem}.auth-story__steps strong,.auth-story__steps small{display:block}.auth-story__steps strong{color:var(--ink-900);font-size:.75rem}.auth-story__steps small{margin-top:.18rem;color:var(--ink-600);font-size:.65rem}.auth-story__steps svg{width:.92rem;color:var(--mint-700)}
.auth-card{width:100%;padding:1.6rem;border-radius:1.7rem;background:linear-gradient(145deg,rgba(255,255,255,.84),rgba(225,248,243,.46));}.auth-card__back{display:inline-flex;align-items:center;gap:.45rem;color:var(--ink-600);font-size:.66rem;font-weight:700}.auth-card__back svg{width:.8rem;transform:rotate(180deg)}.auth-card__heading{margin-top:2.8rem}.auth-card__heading h2{margin:.65rem 0 0;color:var(--ink-900);font-size:2.25rem;letter-spacing:-.06em}.auth-card__heading p{max-width:25rem;margin:.55rem 0 0;color:var(--ink-600);font-size:.82rem;line-height:1.6}.auth-card__modes{display:grid;grid-template-columns:1fr 1fr;gap:.25rem;margin-top:1.7rem;padding:.25rem;border-radius:.75rem;background:rgba(21,40,61,.06)}.auth-card__modes button{height:2.45rem;border:0;border-radius:.57rem;background:transparent;color:var(--ink-600);cursor:pointer;font-size:.7rem;font-weight:760}.auth-card__modes button.active{background:rgba(255,255,255,.96);color:var(--ink-900);box-shadow:var(--shadow-sm)}.auth-form{display:grid;gap:1rem;margin-top:1.3rem}.auth-form__names{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}.auth-form :deep(.ui-button){width:100%;margin-top:.25rem}.auth-card__legal{margin:1.25rem 0 0;color:var(--ink-500);font-size:.61rem;line-height:1.5;text-align:center}
@media(max-width:950px){.auth-page{grid-template-columns:1fr;width:min(calc(100% - 2rem),520px);padding-block:3rem}.auth-story{display:none}}@media(max-width:520px){.auth-page{width:calc(100% - 1.5rem);padding-block:1.5rem}.auth-card{padding:1.15rem;border-radius:1.3rem}.auth-card__heading{margin-top:2.2rem}.auth-form__names{grid-template-columns:1fr}}
</style>
