<template>
  <div class="blockchain-page marketing-page">
    <section class="chain-hero marketing-container">
      <div v-reveal="'left'" class="chain-hero__copy">
        <span class="marketing-kicker">{{ t('blockchain.kicker') }}</span>
        <h1 class="marketing-title">{{ t('blockchain.title') }}<br><em>{{ t('blockchain.titleEm') }}</em></h1>
        <p class="marketing-lede">{{ t('blockchain.lede') }}</p>
        <div class="marketing-action-row">
          <UiButton :to="walletTarget" size="large" icon="wallet">{{ t('blockchain.connectWallet') }}</UiButton>
          <UiButton to="#flow" variant="secondary" size="large">{{ t('blockchain.seeFlow') }}</UiButton>
        </div>
        <p class="chain-hero__note"><UiIcon name="shield" /> {{ t('blockchain.note') }}</p>
      </div>
      <OnchainLedger v-reveal="'right'" :status="blockchain" />
    </section>

    <section class="chain-principles marketing-container marketing-section--tight">
      <div v-reveal class="marketing-section-heading">
        <div><span class="marketing-kicker">{{ t('blockchain.bringsKicker') }}</span><h2>{{ t('blockchain.bringsTitle') }}<br>{{ t('blockchain.bringsTitle2') }}</h2></div>
        <p>{{ t('blockchain.bringsText') }}</p>
      </div>
      <div class="chain-principles__grid">
        <article v-for="item in principles" :key="item.index" class="chain-principle marketing-glass">
          <span class="chain-principle__index">{{ item.index }}</span>
          <span class="chain-principle__icon"><UiIcon :name="item.icon" /></span>
          <h3>{{ item.title }}</h3>
          <p>{{ item.text }}</p>
          <small>{{ item.detail }}</small>
        </article>
      </div>
    </section>

    <section id="flow" class="chain-flow marketing-container marketing-section">
      <div v-reveal class="marketing-section-heading">
        <div><span class="marketing-kicker">{{ t('blockchain.flowKicker') }}</span><h2>{{ t('blockchain.flowTitle') }}<br>{{ t('blockchain.flowTitle2') }}</h2></div>
        <p>{{ t('blockchain.flowText') }}</p>
      </div>
      <ol class="chain-flow__timeline">
        <li v-for="(step, index) in flowSteps" :key="step.label">
          <div class="chain-flow__marker"><span>{{ String(index + 1).padStart(2, '0') }}</span><UiIcon :name="step.icon" /></div>
          <div class="chain-flow__body"><span class="chain-flow__label">{{ step.label }}</span><h3>{{ step.title }}</h3><p>{{ step.text }}</p></div>
          <span v-if="index < flowSteps.length - 1" class="chain-flow__connector" aria-hidden="true"></span>
        </li>
      </ol>
    </section>

    <section class="chain-wallet marketing-container marketing-section--tight">
      <div class="chain-wallet__panel marketing-glass">
        <div class="chain-wallet__copy">
          <span class="marketing-kicker">{{ t('blockchain.walletKicker') }}</span>
          <h2>{{ t('blockchain.walletTitle') }}<br><em>{{ t('blockchain.walletTitleEm') }}</em></h2>
          <p>{{ t('blockchain.walletText') }}</p>
          <div class="marketing-action-row"><UiButton :to="walletTarget" icon="arrow">{{ isAuthenticated ? t('blockchain.openProfile') : t('blockchain.createSpace') }}</UiButton><UiButton to="/service#status" variant="secondary">{{ t('blockchain.paymentStatus') }}</UiButton></div>
        </div>
        <div class="chain-wallet__checks">
          <div v-for="item in walletChecks" :key="item.title"><span><UiIcon :name="item.icon" /></span><p><strong>{{ item.title }}</strong><small>{{ item.text }}</small></p><UiIcon name="check" /></div>
        </div>
      </div>
      <p class="chain-wallet__footnote">{{ blockchain.configured ? t('blockchain.configured') : t('blockchain.notConfigured') }}</p>
    </section>

    <section v-reveal class="chain-cta marketing-container marketing-glass">
      <div><span class="marketing-kicker">{{ t('blockchain.ctaKicker') }}</span><h2>{{ t('blockchain.ctaTitle') }}<br><em>{{ t('blockchain.ctaTitleEm') }}</em></h2><p>{{ t('blockchain.ctaText') }}</p></div>
      <UiButton to="/service" size="large" icon="arrow">{{ t('blockchain.ctaButton') }}</UiButton>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { SystemStatus } from '~/types/api';

definePageMeta({ layout: 'public' });

const { isAuthenticated } = useSession();
const { status, refresh } = useSystemStatus();
const config = useRuntimeConfig();
const blockchain = computed<SystemStatus['blockchain']>(() => status.value?.blockchain || { status: 'unknown', network: 'unknown', configured: false });
const walletTarget = computed(() => isAuthenticated.value ? '/profile' : '/auth?mode=register');
const { t, tl } = useI18n();
const withIcons = <T extends object>(items: T[], icons: string[]) => items.map((item, index) => ({ ...item, icon: icons[index] || 'check', index: `0${index + 1}` }));
const principles = computed(() => withIcons(tl<{ title: string; text: string; detail: string }>('blockchain.principles'), ['processor', 'shield', 'wallet']));
const flowSteps = computed(() => withIcons(tl<{ label: string; title: string; text: string }>('blockchain.flowSteps'), ['upload', 'wallet', 'shield', 'result']));
const walletChecks = computed(() => withIcons(tl<{ title: string; text: string }>('blockchain.walletChecks'), ['wallet', 'shield', 'result']));
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => { refresh(); timer = setInterval(() => refresh(), Math.max(20, Number(config.public.statusRefreshSeconds) || 30) * 1000); });
onBeforeUnmount(() => { if (timer) clearInterval(timer); });
useSeoMeta({ title: () => t('blockchain.seoTitle'), description: () => t('blockchain.seoDescription') });
</script>

<style scoped>
.chain-hero{display:grid;grid-template-columns:minmax(0,1.04fr) minmax(26rem,.96fr);align-items:center;gap:clamp(2.5rem,5vw,5rem);min-height:min(700px,calc(100svh - 5rem));padding-block:clamp(3.5rem,7vw,6rem)}.chain-hero__copy{min-width:0}.chain-hero__copy .marketing-title{max-width:700px;font-size:clamp(2.7rem,4.4vw,4.4rem)}.chain-hero__note{display:flex;align-items:center;gap:.45rem;margin:1.35rem 0 0;color:var(--ink-600);font-size:.9375rem;line-height:1.5}.chain-hero__note svg{width:.85rem;color:var(--violet-600)}
.chain-principles{padding-top:clamp(4rem,7vw,7rem)}.chain-principles__grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}.chain-principle{min-height:18rem;padding:1.35rem;border-radius:1.35rem;background:linear-gradient(145deg,rgba(255,255,255,.72),rgba(239,246,255,.38))}.chain-principle:nth-child(2){background:linear-gradient(145deg,rgba(255,255,255,.72),rgba(238,236,255,.45))}.chain-principle:nth-child(3){background:linear-gradient(145deg,rgba(255,255,255,.72),rgba(239,242,245,.6))}.chain-principle__index{color:var(--ink-400);font-family:var(--font-mono);font-size:.9375rem}.chain-principle__icon{display:grid;width:2.65rem;height:2.65rem;margin-top:2.4rem;place-items:center;border:1px solid rgba(52,133,233,.14);border-radius:.8rem;background:var(--mint-100);color:var(--mint-700);box-shadow:0 8px 18px rgba(52,133,233,.1)}.chain-principle:nth-child(2) .chain-principle__icon{border-color:rgba(106,129,191,.14);background:var(--violet-100);color:var(--violet-600)}.chain-principle:nth-child(3) .chain-principle__icon{background:var(--ink-100);color:var(--ink-700)}.chain-principle__icon svg{width:1.05rem}.chain-principle h3{margin:1.2rem 0 .55rem;color:var(--ink-900);font-size:1.1rem;letter-spacing:-.04em}.chain-principle p{max-width:25rem;margin:0;color:var(--ink-700);font-size:.945rem;line-height:1.7}.chain-principle small{display:block;margin-top:1rem;color:var(--ink-500);font-family:var(--font-mono);font-size:.9375rem;letter-spacing:.03em}
.chain-flow{padding-top:clamp(4rem,8vw,8rem)}.chain-flow__timeline{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin:0;padding:0;list-style:none}.chain-flow__timeline li{position:relative;min-width:0;padding:1.3rem;border:1px solid var(--glass-edge);border-radius:1.25rem;background:rgba(255,255,255,.52);box-shadow:var(--glass-inset),var(--shadow-sm)}.chain-flow__marker{display:flex;align-items:center;justify-content:space-between}.chain-flow__marker span,.chain-flow__label{color:var(--ink-500);font-family:var(--font-mono);font-size:.9375rem;letter-spacing:.07em}.chain-flow__marker svg{width:1.05rem;color:var(--mint-700)}.chain-flow__timeline li:nth-child(2) .chain-flow__marker svg,.chain-flow__timeline li:nth-child(4) .chain-flow__marker svg{color:var(--violet-600)}.chain-flow__body h3{margin:2.6rem 0 .65rem;color:var(--ink-900);font-size:1rem;letter-spacing:-.035em}.chain-flow__body p{margin:0;color:var(--ink-700);font-size:1rem;line-height:1.7}.chain-flow__connector{position:absolute;top:2rem;right:-.65rem;z-index:2;width:1.2rem;height:1px;background:linear-gradient(90deg,var(--mint-500),var(--violet-500))}.chain-flow__connector::after{position:absolute;right:-.05rem;top:-.23rem;width:.45rem;height:.45rem;border-radius:50%;background:var(--violet-500);content:''}
.chain-wallet{padding-top:clamp(3rem,6vw,6rem)}.chain-wallet__panel{display:grid;grid-template-columns:minmax(0,1fr) minmax(20rem,.8fr);gap:clamp(2.5rem,7vw,7rem);align-items:center;padding:clamp(1.5rem,4vw,3.5rem);border-radius:1.7rem;background:linear-gradient(120deg,rgba(255,255,255,.8),rgba(239,246,255,.5) 60%,rgba(238,236,255,.46))}.chain-wallet__copy h2{margin:.9rem 0 0;color:var(--ink-900);font-size:clamp(2.3rem,4.4vw,4.4rem);font-weight:640;line-height:.98;letter-spacing:-.065em}.chain-wallet__copy h2 em{color:var(--ink-500);font-style:normal;font-weight:560}.chain-wallet__copy>p{max-width:570px;margin:1.35rem 0 0;color:var(--ink-700);font-size:1rem;line-height:1.78}.chain-wallet__checks{display:grid;gap:.6rem}.chain-wallet__checks>div{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.7rem;padding:.85rem;border:1px solid rgba(255,255,255,.8);border-radius:.9rem;background:rgba(255,255,255,.55)}.chain-wallet__checks>div>span{display:grid;width:2.3rem;height:2.3rem;place-items:center;border-radius:.7rem;background:var(--mint-100);color:var(--mint-700)}.chain-wallet__checks>div:nth-child(2)>span{background:var(--violet-100);color:var(--violet-600)}.chain-wallet__checks>div:nth-child(3)>span{background:var(--ink-100);color:var(--ink-700)}.chain-wallet__checks svg{width:.9rem}.chain-wallet__checks p{margin:0}.chain-wallet__checks strong,.chain-wallet__checks small{display:block}.chain-wallet__checks strong{color:var(--ink-900);font-size:.9375rem}.chain-wallet__checks small{margin-top:.25rem;color:var(--ink-600);font-size:.9375rem;line-height:1.4}.chain-wallet__checks>div>svg{color:var(--mint-700)}.chain-wallet__footnote{margin:.9rem .25rem 0;color:var(--ink-500);font-size:.9375rem;line-height:1.6}
.chain-cta{display:flex;align-items:center;justify-content:space-between;gap:2rem;margin-top:clamp(4rem,8vw,8rem);padding:clamp(1.75rem,4vw,3.4rem);border-radius:1.8rem;background:linear-gradient(120deg,rgba(255,255,255,.82),rgba(239,246,255,.6) 55%,rgba(238,236,255,.56))}.chain-cta h2{margin:.9rem 0 0;color:var(--ink-900);font-size:clamp(1.9rem,3.7vw,3.4rem);font-weight:640;line-height:1.02;letter-spacing:-.06em}.chain-cta h2 em{color:var(--ink-500);font-style:normal;font-weight:560}.chain-cta p{max-width:520px;margin:.9rem 0 0;color:var(--ink-700);font-size:.983rem;line-height:1.7}.chain-cta :deep(.ui-button){flex:none}
@media(max-width:1050px){.chain-hero{grid-template-columns:1fr;min-height:auto;gap:3.5rem}.chain-hero__copy{max-width:800px}.chain-hero :deep(.onchain-ledger){max-width:800px;width:100%;margin-inline:auto}.chain-flow__timeline{grid-template-columns:repeat(2,1fr)}.chain-flow__connector{display:none}}
@media(max-width:760px){.chain-hero{padding-block:3.5rem 4.5rem}.chain-principles__grid{grid-template-columns:1fr}.chain-principle{min-height:0}.chain-principle__icon{margin-top:1.6rem}.chain-wallet__panel{grid-template-columns:1fr;gap:2rem}.chain-cta{align-items:flex-start;flex-direction:column}.chain-cta :deep(.ui-button){width:100%}}
@media(max-width:520px){.chain-hero{padding-block:3rem 4rem}.chain-hero__copy .marketing-title{font-size:clamp(2.85rem,11.8vw,4.4rem)}.chain-flow__timeline{grid-template-columns:1fr}.chain-flow__timeline li{padding:1.1rem}.chain-wallet__panel{border-radius:1.35rem;padding:1.2rem}.chain-wallet__copy h2{font-size:clamp(2.45rem,12.5vw,4rem)}.chain-cta{border-radius:1.35rem}}
</style>
