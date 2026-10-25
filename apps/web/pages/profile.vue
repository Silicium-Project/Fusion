<template>
  <div class="app-page">
    <header>
      <span class="eyebrow">{{ t('nav.account') }}</span>
      <h1 class="page-title">{{ t('nav.settings') }}</h1>
      <p class="page-intro">{{ t('profile.intro') }}</p>
    </header>
    <UiNotice v-if="pageNotice.message" :tone="pageNotice.tone">{{ pageNotice.message }}</UiNotice>
    <div class="profile-layout">
      <section class="profile-summary surface">
        <div class="profile-summary__avatar">{{ initials }}</div>
        <h2>{{ displayName }}</h2>
        <p>{{ user?.email }}</p>
        <UiStatusBadge
          :status="user?.walletAddress ? 'verified' : 'unknown'"
          :label="user?.walletAddress ? t('profile.walletVerified') : t('profile.walletMissing')"
        />
        <dl>
          <div>
            <dt>{{ t('profile.memberSince') }}</dt>
            <dd>{{ formatDate(user?.createdAt, false) }}</dd>
          </div>
          <div>
            <dt>{{ t('profile.role') }}</dt>
            <dd>{{ user?.role || t('profile.defaultRole') }}</dd>
          </div>
        </dl>
        <UiButton variant="ghost" icon="logout" @click="logout">{{ t('profile.logout') }}</UiButton>
      </section>
      <div class="stack">
        <UiCard :title="t('profile.personal')" :description="t('profile.personalText')" padded
          ><form class="profile-form" novalidate @submit.prevent="saveIdentity">
            <div class="profile-form__grid">
              <label class="field"
                ><span>{{ t('auth.firstName') }}</span
                ><input
                  v-model.trim="identity.firstName"
                  class="input"
                  autocomplete="given-name"
                  :maxlength="LIMITS.personName" /></label
              ><label class="field"
                ><span>{{ t('auth.lastName') }}</span
                ><input
                  v-model.trim="identity.lastName"
                  class="input"
                  autocomplete="family-name"
                  :maxlength="LIMITS.personName"
              /></label>
            </div>
            <label class="field"
              ><span>{{ t('auth.username') }}</span
              ><input
                v-model.trim="identity.username"
                class="input"
                autocomplete="username"
                :maxlength="LIMITS.username"
                aria-describedby="profile-username-hint"
              /><small id="profile-username-hint" class="field-hint">{{
                t('auth.usernameHint')
              }}</small></label
            ><label class="field"
              ><span>{{ t('profile.email') }}</span
              ><input :value="user?.email" class="input" disabled /></label
            ><UiButton type="submit" :loading="savingIdentity">{{ t('profile.save') }}</UiButton>
          </form></UiCard
        >
        <UiCard :title="t('profile.security')" :description="t('profile.securityText')" padded
          ><form class="profile-form" novalidate @submit.prevent="savePassword">
            <label class="field"
              ><span>{{ t('profile.currentPassword') }}</span
              ><UiPasswordInput
                v-model="password.current"
                class="input"
                autocomplete="current-password"
                maxlength="128"
                required
            /></label>
            <div class="profile-form__grid">
              <label class="field"
                ><span>{{ t('profile.newPassword') }}</span
                ><UiPasswordInput
                  v-model="password.next"
                  class="input"
                  autocomplete="new-password"
                  :minlength="LIMITS.passwordMin"
                  maxlength="128"
                  required /></label
              ><label class="field"
                ><span>{{ t('profile.confirmation') }}</span
                ><UiPasswordInput
                  v-model="password.confirm"
                  class="input"
                  autocomplete="new-password"
                  :minlength="LIMITS.passwordMin"
                  maxlength="128"
                  required
              /></label>
            </div>
            <UiButton type="submit" variant="secondary" :loading="savingPassword">{{
              t('profile.updatePassword')
            }}</UiButton>
          </form></UiCard
        >
        <SILEconomyPanel
          :wallet-address="user?.walletAddress || ''"
          :sol-balance="balance"
          :sil-balance="silBalance"
          @refresh-balances="wallet.loadBalance(user?.walletAddress)"
        />
      </div>
      <aside class="stack">
        <UiCard :title="t('profile.wallet')" :description="t('profile.walletText')" padded
          ><div class="wallet-card">
            <span class="wallet-card__icon"><UiIcon name="wallet" /></span
            ><template v-if="user?.walletAddress"
              ><strong class="mono">{{ compactIdentifier(user.walletAddress, 10, 8) }}</strong
              ><small>{{ t('profile.walletProof') }}</small>
              <div class="wallet-card__balances">
                <div class="wallet-card__balance">
                  <span>{{ t('profile.solBalance') }}</span
                  ><strong>{{ balance === null ? '—' : `${balance.toFixed(4)} SOL` }}</strong>
                </div>
                <div class="wallet-card__balance">
                  <span>{{ t('profile.silBalance') }}</span
                  ><strong>{{ silBalance === null ? '—' : `${silBalance.toFixed(2)} SIL` }}</strong>
                </div>
              </div>
              <UiButton
                variant="secondary"
                size="small"
                :loading="connecting"
                @click="connectWallet"
                >{{ t('profile.verifyAgain') }}</UiButton
              ></template
            ><template v-else
              ><strong>{{ t('profile.noWallet') }}</strong
              ><small>{{ t('profile.noWalletText') }}</small
              ><UiButton icon="wallet" :loading="connecting" @click="connectWallet">{{
                t('profile.connectPhantom')
              }}</UiButton></template
            >
          </div>
          <UiNotice v-if="balanceError" tone="warning">{{ balanceError }}</UiNotice
          ><UiNotice v-if="walletError" tone="danger">{{ walletError }}</UiNotice></UiCard
        >
        <UiCard :title="t('profile.session')" padded
          ><dl class="session-details">
            <div>
              <dt>{{ t('profile.renewal') }}</dt>
              <dd>{{ t('profile.automatic') }}</dd>
            </div>
            <div>
              <dt>{{ t('profile.accessDuration') }}</dt>
              <dd>{{ t('profile.minutes15') }}</dd>
            </div>
            <div>
              <dt>{{ t('profile.longSession') }}</dt>
              <dd>{{ t('profile.days7') }}</dd>
            </div>
          </dl></UiCard
        >
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { compactIdentifier, formatDate } from '~/utils/format';
import { extractJobError } from '~/utils/jobs';
import {
  firstProblem,
  LIMITS,
  newPasswordProblem,
  personNameProblem,
  usernameProblem,
} from '~/utils/validation';
definePageMeta({ layout: 'app', middleware: 'auth' });
const router = useRouter();
const session = useSession();
const wallet = useWallet();
const { t } = useI18n();
const { user, displayName, initials } = session;
const { connecting, balance, silBalance, balanceError, error: walletError } = wallet;
const savingIdentity = ref(false);
const savingPassword = ref(false);
const identity = reactive({ firstName: '', lastName: '', username: '' });
const password = reactive({ current: '', next: '', confirm: '' });
const pageNotice = reactive<{ message: string; tone: 'success' | 'danger' }>({
  message: '',
  tone: 'success',
});
function notify(tone: 'success' | 'danger', message: string) {
  pageNotice.tone = tone;
  pageNotice.message = message;
}
function hydrateIdentity() {
  identity.firstName = user.value?.firstName || '';
  identity.lastName = user.value?.lastName || '';
  identity.username = user.value?.username || '';
}
async function saveIdentity() {
  pageNotice.message = '';
  const problem = firstProblem(
    personNameProblem(identity.firstName),
    personNameProblem(identity.lastName),
    usernameProblem(identity.username),
  );
  if (problem) {
    notify('danger', t(problem));
    return;
  }
  savingIdentity.value = true;
  try {
    await session.saveProfile({
      firstName: identity.firstName,
      lastName: identity.lastName,
      username: identity.username,
    });
    notify('success', t('profile.saved'));
  } catch (failure) {
    notify('danger', extractJobError(failure, t('profile.saveFailed')));
  } finally {
    savingIdentity.value = false;
  }
}
async function savePassword() {
  pageNotice.message = '';
  if (password.next !== password.confirm) {
    notify('danger', t('validation.passwordMismatch'));
    return;
  }
  const problem = newPasswordProblem(password.next);
  if (problem) {
    notify('danger', t(problem));
    return;
  }
  savingPassword.value = true;
  try {
    await session.changePassword(password.current, password.next);
    password.current = '';
    password.next = '';
    password.confirm = '';
    notify('success', t('profile.passwordUpdated'));
  } catch (failure) {
    notify('danger', extractJobError(failure, t('profile.passwordFailed')));
  } finally {
    savingPassword.value = false;
  }
}
async function connectWallet() {
  pageNotice.message = '';
  try {
    await wallet.connect();
    notify('success', t('profile.walletConnected'));
  } catch {
    /* The composable exposes a contextual message. */
  }
}
async function logout() {
  session.clearSession();
  await router.push('/');
}
let balanceTimer: ReturnType<typeof setInterval> | undefined;
onMounted(async () => {
  await session.loadUser().catch(() => undefined);
  hydrateIdentity();
  await wallet.loadBalance(user.value?.walletAddress);
  balanceTimer = setInterval(() => {
    if (document.visibilityState === 'visible') wallet.loadBalance(user.value?.walletAddress);
  }, 30_000);
});
onBeforeUnmount(() => {
  if (balanceTimer) clearInterval(balanceTimer);
});
watch(user, hydrateIdentity);
watch(
  () => user.value?.walletAddress,
  (address) => {
    if (address) wallet.loadBalance(address);
  },
);
useSeoMeta({ title: () => t('profile.seoTitle') });
</script>

<style scoped>
.profile-summary {
  grid-template-columns: minmax(0, 1fr);
}
.profile-summary :deep(.status-badge) {
  width: auto;
  max-width: 100%;
  white-space: normal;
  line-height: 1.45;
  font-size: 0.9375rem;
  justify-content: center;
}
.profile-summary dl {
  min-width: 0;
}
.profile-summary dl > div {
  gap: 0.65rem;
  align-items: start;
}
.profile-summary dd {
  max-width: 55%;
  overflow-wrap: anywhere;
  text-align: right;
}

.profile-layout {
  display: grid;
  grid-template-columns: 220px minmax(300px, 1fr) minmax(220px, 0.72fr);
  align-items: start;
  gap: 1rem;
}
.profile-summary {
  position: sticky;
  top: 6rem;
  display: grid;
  justify-items: center;
  padding: 1.4rem;
  text-align: center;
}
.profile-summary__avatar {
  display: grid;
  width: 4.4rem;
  height: 4.4rem;
  place-items: center;
  border-radius: 1.25rem;
  background: var(--violet-100);
  color: var(--violet-600);
  font-size: 1.2rem;
  font-weight: 850;
}
.profile-summary {
  min-width: 0;
}
.profile-summary h2 {
  max-width: 100%;
  margin: 1rem 0 0.2rem;
  overflow-wrap: anywhere;
  font-size: 1rem;
}
.profile-summary > p {
  max-width: 100%;
  margin: 0 0 0.8rem;
  overflow-wrap: anywhere;
  color: var(--ink-500);
  font-size: 1rem;
}
.profile-summary dl {
  width: 100%;
  margin: 1.2rem 0;
}
.profile-summary dl > div {
  display: flex;
  justify-content: space-between;
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.9375rem;
}
.profile-summary dt {
  color: var(--ink-500);
}
.profile-summary dd {
  margin: 0;
  font-weight: 700;
}
.profile-summary :deep(.ui-button) {
  width: 100%;
}
.profile-form {
  display: grid;
  gap: 1rem;
}
.field-hint {
  color: var(--ink-500);
  font-size: 0.9375rem;
  line-height: 1.4;
}
.profile-form__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.8rem;
}
.profile-form :deep(.ui-button) {
  justify-self: end;
}
.wallet-card {
  display: grid;
  justify-items: center;
  text-align: center;
}
.wallet-card__icon {
  display: grid;
  width: 3rem;
  height: 3rem;
  place-items: center;
  border-radius: 0.85rem;
  background: var(--mint-100);
  color: var(--mint-700);
}
.wallet-card__icon svg {
  width: 1.2rem;
}
.wallet-card > strong {
  max-width: 100%;
  margin-top: 0.9rem;
  overflow: hidden;
  font-size: 0.9375rem;
  text-overflow: ellipsis;
}
.wallet-card > small {
  margin: 0.3rem 0 1rem;
  color: var(--ink-500);
  font-size: 0.9375rem;
  line-height: 1.5;
}
.wallet-card__balance {
  width: 100%;
  margin-bottom: 1rem;
  padding: 0.75rem;
  border-radius: 0.65rem;
  background: var(--surface-soft);
}
.wallet-card__balance span,
.wallet-card__balance strong {
  display: block;
}
.wallet-card__balance span {
  color: var(--ink-500);
  font-size: 0.9375rem;
}
.wallet-card__balance strong {
  margin-top: 0.2rem;
  font-size: 0.966rem;
}
.session-details {
  margin: 0;
}
.session-details > div {
  display: flex;
  justify-content: space-between;
  padding: 0.55rem 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.9375rem;
}
.session-details > div:last-child {
  border: 0;
}
.session-details dt {
  color: var(--ink-500);
}
.session-details dd {
  margin: 0;
  font-weight: 700;
}
@media (max-width: 1120px) {
  .profile-layout {
    grid-template-columns: 210px 1fr;
  }
  .profile-layout > aside {
    grid-column: 2;
  }
}
@media (max-width: 740px) {
  .profile-layout {
    grid-template-columns: 1fr;
  }
  .profile-summary {
    position: static;
  }
  .profile-layout > aside {
    grid-column: auto;
  }
  .profile-form__grid {
    grid-template-columns: 1fr;
  }
}
.wallet-card__balances {
  display: grid;
  width: 100%;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
.wallet-card__balances .wallet-card__balance {
  margin: 0;
}
.wallet-card__balance strong {
  font-size: 1.05rem;
}
</style>
