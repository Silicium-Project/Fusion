<template>
  <main class="auth-page marketing-page">
    <section v-reveal="'left'" class="auth-story">
      <span class="marketing-kicker">{{ t('auth.kicker') }}</span>
      <h1 class="marketing-title">{{ t('auth.title') }}<br><em>{{ t('auth.titleEm') }}</em></h1>
      <p class="marketing-lede">{{ t('auth.lede') }}</p>
      <ol class="auth-story__steps"><li v-for="(item,index) in story" :key="index"><span>{{ String(index + 1).padStart(2,'0') }}</span><div><strong>{{ item.title }}</strong><small>{{ item.text }}</small></div><UiIcon :name="item.icon" /></li></ol>
    </section>
    <section v-reveal="'right'" class="auth-card marketing-glass">
      <NuxtLink to="/" class="auth-card__back"><UiIcon name="arrow" />{{ t('auth.backHome') }}</NuxtLink>
      <div class="auth-card__heading"><span class="marketing-kicker">{{ isLogin ? t('auth.loginKicker') : t('auth.registerKicker') }}</span><h2>{{ isLogin ? t('auth.loginTitle') : t('auth.registerTitle') }}</h2><p>{{ isLogin ? t('auth.loginText') : t('auth.registerText') }}</p></div>
      <div class="auth-card__modes" role="tablist" :aria-label="t('auth.modes')" @keydown="switchModeWithArrows"><button id="auth-tab-login" ref="loginTab" type="button" role="tab" aria-controls="auth-form" :aria-selected="isLogin" :tabindex="isLogin ? 0 : -1" :class="{ active: isLogin }" @click="setMode('login')">{{ t('auth.login') }}</button><button id="auth-tab-register" ref="registerTab" type="button" role="tab" aria-controls="auth-form" :aria-selected="!isLogin" :tabindex="isLogin ? -1 : 0" :class="{ active: !isLogin }" @click="setMode('register')">{{ t('auth.register') }}</button></div>
      <form id="auth-form" class="auth-form" role="tabpanel" :aria-labelledby="isLogin ? 'auth-tab-login' : 'auth-tab-register'" :aria-busy="submitting" novalidate @submit.prevent="submit">
        <div v-if="!isLogin" class="auth-form__names"><label class="field"><span>{{ t('auth.firstName') }}</span><input v-model.trim="form.firstName" class="input" autocomplete="given-name" required :maxlength="LIMITS.personName" :placeholder="t('auth.firstName')"></label><label class="field"><span>{{ t('auth.lastName') }}</span><input v-model.trim="form.lastName" class="input" autocomplete="family-name" required :maxlength="LIMITS.personName" :placeholder="t('auth.lastNamePlaceholder')"></label></div>
        <label v-if="!isLogin" class="field"><span>{{ t('auth.username') }}</span><input v-model.trim="form.username" class="input" autocomplete="username" required minlength="3" :maxlength="LIMITS.username" pattern="[A-Za-z0-9._\-]{3,30}" :placeholder="t('auth.username')" aria-describedby="username-hint"><small id="username-hint" class="field-hint">{{ t('auth.usernameHint') }}</small></label>
        <label class="field"><span>{{ isLogin ? t('auth.identifier') : t('auth.email') }}</span><input v-if="isLogin" v-model.trim="form.identifier" class="input" autocomplete="username" required :maxlength="LIMITS.email" :placeholder="t('auth.identifier')"><input v-else v-model.trim="form.email" class="input" type="email" autocomplete="email" required :maxlength="LIMITS.email" :placeholder="t('auth.emailPlaceholder')"></label>
        <label class="field"><span>{{ t('auth.password') }}</span><input v-model="form.password" class="input" type="password" :autocomplete="isLogin ? 'current-password' : 'new-password'" :minlength="isLogin ? undefined : LIMITS.passwordMin" maxlength="128" required :placeholder="t('auth.passwordPlaceholder')"></label>
        <UiNotice v-if="error" tone="danger">{{ error }}</UiNotice><UiNotice v-if="success" tone="success">{{ success }}</UiNotice>
        <UiButton type="submit" size="large" icon="arrow" :loading="submitting">{{ isLogin ? t('auth.submitLogin') : t('auth.submitRegister') }}</UiButton>
      </form>
      <p class="auth-card__legal">{{ t('auth.legal') }}</p>
    </section>
  </main>
</template>

<script setup lang="ts">
import { safeRedirect } from '~/utils/auth';
import { emailProblem, firstProblem, LIMITS, newPasswordProblem, personNameProblem, usernameProblem } from '~/utils/validation';
definePageMeta({ layout: 'auth', middleware: 'guest' });
const route = useRoute();
const router = useRouter();
const session = useSession();
const { t, tl } = useI18n();
const isLogin = computed(() => route.query.mode !== 'register');
const submitting = ref(false);
const error = ref('');
const success = ref('');
const form = reactive({ firstName: '', lastName: '', username: '', email: '', identifier: '', password: '' });
const storyIcons = ['upload', 'network', 'shield'];
const story = computed(() => tl<{ title: string; text: string }>('auth.story').map((item, index) => ({ ...item, icon: storyIcons[index] || 'check' })));
const loginTab = ref<HTMLButtonElement | null>(null);
const registerTab = ref<HTMLButtonElement | null>(null);
/**
 * The two modes are tabs: one stop for the Tab key (the active one), the
 * arrow keys switch, so that a focused tab is never mistaken for the shown
 * form.
 */
async function switchModeWithArrows(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const mode = event.key === 'Home' ? 'login' : event.key === 'End' ? 'register' : isLogin.value ? 'register' : 'login';
  await setMode(mode);
  (mode === 'login' ? loginTab : registerTab).value?.focus();
}
async function setMode(mode: 'login' | 'register') { error.value = ''; success.value = ''; form.password = ''; await router.replace({ path: '/auth', query: { ...route.query, mode } }); }
/** The first problem of the registration form, as a message; '' when it can be sent. */
function registrationProblem(): string {
  const key = firstProblem(
    personNameProblem(form.firstName), personNameProblem(form.lastName),
    form.username.trim() ? usernameProblem(form.username) : 'validation.usernameInvalid',
    emailProblem(form.email), newPasswordProblem(form.password),
  );
  return key ? t(key) : '';
}
async function submit() {
  if (submitting.value) return;
  error.value = ''; success.value = '';
  if (!isLogin.value) { error.value = registrationProblem(); if (error.value) return; }
  else if (!form.identifier.trim() || !form.password) { error.value = t('auth.checkForm'); return; }
  submitting.value = true;
  try {
    if (isLogin.value) {
      await session.login(form.identifier, form.password);
      await router.push(safeRedirect(route.query.redirect));
    } else {
      await session.register({ email: form.email.trim(), password: form.password, username: form.username.trim(), first_name: form.firstName.trim(), last_name: form.lastName.trim() });
      form.identifier = form.email.trim();
      await setMode('login');
      success.value = t('auth.created');
    }
  } catch (failure) { error.value = session.errorMessage(failure); }
  finally { submitting.value = false; }
}
useSeoMeta({ title: () => `${isLogin.value ? t('auth.seoLogin') : t('auth.seoRegister')} — Silicium`, description: () => t('auth.seoDescription') });
</script>

<style scoped>
.auth-page{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(28rem,.72fr);align-items:center;gap:clamp(2.5rem,6vw,6rem);width:min(calc(100% - 3rem),1240px);min-height:100vh;margin:auto;padding:5rem 0 3rem}.auth-story{min-width:0;max-width:700px}.auth-story .marketing-title{max-width:640px;font-size:clamp(3rem,4.9vw,5.4rem)}.auth-story__steps{display:grid;max-width:580px;gap:.65rem;margin:2.2rem 0 0;padding:0;list-style:none}.auth-story__steps li{display:grid;grid-template-columns:2rem 1fr auto;align-items:center;gap:.8rem;padding:.7rem 0;border-top:1px solid var(--border)}.auth-story__steps li:last-child{border-bottom:1px solid var(--border)}.auth-story__steps>li>span{color:var(--ink-400);font-family:var(--font-mono);font-size:.58rem}.auth-story__steps strong,.auth-story__steps small{display:block}.auth-story__steps strong{color:var(--ink-900);font-size:.75rem}.auth-story__steps small{margin-top:.18rem;color:var(--ink-600);font-size:.65rem}.auth-story__steps svg{width:.92rem;color:var(--mint-700)}
.auth-card{width:100%;padding:1.6rem;border-radius:1.7rem;background:linear-gradient(145deg,rgba(255,255,255,.84),rgba(225,248,243,.46));}.auth-card__back{display:inline-flex;align-items:center;gap:.45rem;color:var(--ink-600);font-size:.66rem;font-weight:700}.auth-card__back svg{width:.8rem;transform:rotate(180deg)}.auth-card__heading{margin-top:2.8rem}.auth-card__heading h2{margin:.65rem 0 0;color:var(--ink-900);font-size:2.25rem;letter-spacing:-.06em}.auth-card__heading p{max-width:25rem;margin:.55rem 0 0;color:var(--ink-600);font-size:.82rem;line-height:1.6}.auth-card__modes{display:grid;grid-template-columns:1fr 1fr;gap:.25rem;margin-top:1.7rem;padding:.25rem;border-radius:.75rem;background:rgba(21,40,61,.06)}.auth-card__modes button{height:2.45rem;border:0;border-radius:.57rem;background:transparent;color:var(--ink-600);cursor:pointer;font-size:.7rem;font-weight:760}.auth-card__modes button.active{background:rgba(255,255,255,.96);color:var(--ink-900);box-shadow:var(--shadow-sm)}.auth-card__modes button:focus-visible{outline:2px solid var(--mint-600);outline-offset:-2px;box-shadow:none}.auth-form{display:grid;gap:1rem;margin-top:1.3rem}.auth-form__names{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}.auth-form :deep(.ui-button){width:100%;margin-top:.25rem}.field-hint{color:var(--ink-500);font-size:.6rem;line-height:1.4}.auth-card__legal{margin:1.25rem 0 0;color:var(--ink-500);font-size:.61rem;line-height:1.5;text-align:center}
@media(max-width:950px){.auth-page{grid-template-columns:1fr;width:min(calc(100% - 2rem),520px);padding-block:3rem}.auth-story{display:none}}@media(max-width:520px){.auth-page{width:calc(100% - 1.5rem);padding-block:1.5rem}.auth-card{padding:1.15rem;border-radius:1.3rem}.auth-card__heading{margin-top:2.2rem}.auth-form__names{grid-template-columns:1fr}}
</style>
