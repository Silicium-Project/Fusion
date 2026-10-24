<template>
  <article class="onchain-ledger marketing-glass" :class="{ 'onchain-ledger--compact': compact }" :aria-label="t('ledger.aria')">
    <header class="onchain-ledger__header">
      <div>
        <span class="onchain-ledger__eyebrow"><i></i>Solana / {{ networkLabel }}</span>
          <strong>{{ t('ledger.title') }}</strong>
      </div>
      <UiStatusBadge :status="chain.status" :label="chainStatusLabel" />
    </header>

    <div class="onchain-ledger__body">
      <div class="onchain-ledger__hero-row">
        <span class="onchain-ledger__seal"><UiIcon name="shield" /></span>
        <div>
          <span class="onchain-ledger__micro-label">{{ t('ledger.solana') }}</span>
          <strong>{{ chain.configured ? t('ledger.enabled') : t('ledger.available') }}</strong>
          <small>{{ programLabel }}</small>
        </div>
      </div>

      <div class="onchain-ledger__rail" aria-hidden="true"><span></span><i></i><span></span></div>

      <div class="onchain-ledger__entries">
        <div>
          <span class="onchain-ledger__entry-icon onchain-ledger__entry-icon--mint"><UiIcon name="upload" /></span>
          <p><strong>{{ entries[0]?.title }}</strong><small>{{ entries[0]?.text }}</small></p>
          <b>01</b>
        </div>
        <div>
          <span class="onchain-ledger__entry-icon onchain-ledger__entry-icon--violet"><UiIcon name="layers" /></span>
          <p><strong>{{ entries[1]?.title }}</strong><small>{{ entries[1]?.text }}</small></p>
          <b>02</b>
        </div>
        <div>
          <span class="onchain-ledger__entry-icon onchain-ledger__entry-icon--ink"><UiIcon name="wallet" /></span>
          <p><strong>{{ entries[2]?.title }}</strong><small>{{ entries[2]?.text }}</small></p>
          <b>03</b>
        </div>
      </div>
    </div>

    <footer class="onchain-ledger__footer">
      <span><i></i>{{ t('ledger.signed') }}</span>
      <small>{{ compact ? t('ledger.verifiable') : t('ledger.trail') }}</small>
    </footer>
  </article>
</template>

<script setup lang="ts">
import type { SystemStatus } from '~/types/api';
import { compactIdentifier, statusLabel } from '~/utils/format';

const props = withDefaults(defineProps<{ compact?: boolean; status?: SystemStatus['blockchain'] | null }>(), { compact: false });
const { t, tl } = useI18n();
const entries = computed(() => tl<{ title: string; text: string }>('ledger.entries'));
const chain = computed(() => ({
  status: props.status?.status || 'unknown',
  network: props.status?.network || 'unknown',
  configured: Boolean(props.status?.configured),
  programId: props.status?.programId,
}));
const networkLabel = computed(() => chain.value.network.charAt(0).toUpperCase() + chain.value.network.slice(1));
const chainStatusLabel = computed(() => statusLabel(chain.value.status));
const programLabel = computed(() => chain.value.programId ? compactIdentifier(chain.value.programId, 10, 8) : t('ledger.programFallback'));
</script>

<style scoped>
.onchain-ledger{border-radius:1.8rem;background:linear-gradient(145deg,rgba(255,255,255,.84),rgba(239,246,255,.54) 58%,rgba(238,236,255,.52));}
.onchain-ledger__header{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;padding:1.35rem 1.4rem 1.15rem;border-bottom:1px solid var(--border)}
.onchain-ledger__header strong{display:block;margin-top:.45rem;color:var(--ink-900);font-size:1.08rem;letter-spacing:-.04em}.onchain-ledger__eyebrow{display:flex;align-items:center;gap:.42rem;color:var(--ink-600);font-family:var(--font-mono);font-size:.9375rem;font-weight:650;letter-spacing:.08em;text-transform:uppercase}.onchain-ledger__eyebrow i{width:.38rem;height:.38rem;border-radius:50%;background:var(--violet-500);box-shadow:0 0 0 .24rem rgba(106,129,191,.1)}
.onchain-ledger__body{padding:1.4rem}.onchain-ledger__hero-row{display:flex;align-items:center;gap:.8rem}.onchain-ledger__seal{display:grid;width:3rem;height:3rem;place-items:center;border:1px solid rgba(106,129,191,.18);border-radius:.95rem;background:linear-gradient(145deg,var(--violet-100),rgba(255,255,255,.82));color:var(--violet-600);box-shadow:inset 0 1px 0 rgba(255,255,255,.9),0 10px 22px rgba(106,129,191,.11)}.onchain-ledger__seal svg{width:1.25rem}.onchain-ledger__hero-row strong,.onchain-ledger__hero-row small{display:block}.onchain-ledger__micro-label{color:var(--ink-500);font-family:var(--font-mono);font-size:.9375rem;letter-spacing:.08em}.onchain-ledger__hero-row strong{margin-top:.22rem;color:var(--ink-900);font-size:.952rem;letter-spacing:-.025em}.onchain-ledger__hero-row small{margin-top:.18rem;color:var(--ink-600);font-family:var(--font-mono);font-size:.9375rem}
.onchain-ledger__rail{display:flex;align-items:center;gap:.35rem;margin:1.25rem 0 1.1rem;padding-left:1.3rem}.onchain-ledger__rail span{width:.42rem;height:.42rem;border:1px solid rgba(255,255,255,.95);border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 .22rem rgba(52,133,233,.1)}.onchain-ledger__rail i{width:calc(100% - 1.2rem);height:1px;background:linear-gradient(90deg,rgba(52,133,233,.42),rgba(106,129,191,.42));position:relative}.onchain-ledger__rail i::after{position:absolute;top:-.22rem;left:24%;width:.45rem;height:.45rem;border-radius:50%;background:var(--violet-500);box-shadow:0 0 0 .22rem rgba(106,129,191,.1);content:'';animation:none}
.onchain-ledger__entries{display:grid;gap:.58rem}.onchain-ledger__entries>div{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.72rem;padding:.68rem;border:1px solid rgba(255,255,255,.75);border-radius:.82rem;background:rgba(255,255,255,.54);box-shadow:inset 0 1px 0 rgba(255,255,255,.9)}.onchain-ledger__entry-icon{display:grid;width:2.15rem;height:2.15rem;place-items:center;border-radius:.68rem}.onchain-ledger__entry-icon--mint{background:var(--mint-100);color:var(--mint-700)}.onchain-ledger__entry-icon--violet{background:var(--violet-100);color:var(--violet-600)}.onchain-ledger__entry-icon--ink{background:var(--ink-100);color:var(--ink-700)}.onchain-ledger__entry-icon svg{width:.92rem}.onchain-ledger__entries p{margin:0}.onchain-ledger__entries strong,.onchain-ledger__entries small{display:block}.onchain-ledger__entries strong{color:var(--ink-900);font-size:.9375rem}.onchain-ledger__entries small{margin-top:.22rem;color:var(--ink-600);font-size:.9375rem}.onchain-ledger__entries b{color:var(--ink-400);font-family:var(--font-mono);font-size:.9375rem;font-weight:500}
.onchain-ledger__footer{display:flex;align-items:center;justify-content:space-between;gap:.75rem;padding:.9rem 1.4rem 1.1rem;border-top:1px solid var(--border);color:var(--ink-600);font-size:.9375rem}.onchain-ledger__footer span{display:flex;align-items:center;gap:.4rem}.onchain-ledger__footer span i{width:.38rem;height:.38rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 .2rem rgba(52,133,233,.1)}.onchain-ledger__footer small{color:var(--ink-500);font-family:var(--font-mono);font-size:.9375rem;letter-spacing:.04em}
.onchain-ledger--compact .onchain-ledger__body{padding:1.15rem 1.2rem}.onchain-ledger--compact .onchain-ledger__header{padding:1.1rem 1.2rem}.onchain-ledger--compact .onchain-ledger__footer{padding-inline:1.2rem}.onchain-ledger--compact .onchain-ledger__entries strong{font-size:.9375rem}
@keyframes onchain-pulse{0%,100%{transform:translateX(0);opacity:.55}50%{transform:translateX(16px);opacity:1}}
@media(max-width:520px){.onchain-ledger{border-radius:1.35rem}.onchain-ledger__header{padding:1rem}.onchain-ledger__body{padding:1rem}.onchain-ledger__footer{align-items:flex-start;flex-direction:column;padding: .8rem 1rem 1rem}.onchain-ledger__footer small{font-size:.9375rem}.onchain-ledger__entries strong{font-size:.9375rem}}
</style>
