<template>
  <UiCard :title="t('profile.economyTitle')" :description="t('profile.economyText')" padded>
    <div class="sil-economy">
      <div class="sil-economy__market" aria-live="polite">
        <div class="sil-economy__price">
          <span>{{ t('profile.economyPrice') }}</span>
          <strong>{{
            market?.silUsd === null || market?.silUsd === undefined ? '—' : usd(market.silUsd)
          }}</strong>
          <small>{{
            market?.oracleAvailable
              ? t('profile.economyPythFresh', { seconds: market.pythAgeSeconds ?? 0 })
              : t('profile.economyPythUnavailable')
          }}</small>
        </div>
        <div class="sil-economy__rate">
          <span>{{ t('profile.economyRate') }}</span>
          <strong>{{ market ? `${number(market.silPerSol, 2)} SIL` : '—' }}</strong>
          <small>{{
            market ? `1 SOL ≈ ${number(market.silPerSol, 2)} SIL` : t('profile.economyLoading')
          }}</small>
        </div>
      </div>

      <div class="sil-economy__basis">
        <p>{{ t('profile.economyCreditMapping') }}</p>
        <p>{{ t('profile.economyRewardText') }}</p>
      </div>

      <UiNotice v-if="marketError" tone="warning">{{ t('profile.economyMarketError') }}</UiNotice>

      <form class="sil-economy__swap" @submit.prevent="submitSwap">
        <div
          class="sil-economy__directions"
          role="group"
          :aria-label="t('profile.economyDirection')"
        >
          <button
            type="button"
            :class="{ 'is-active': direction === 'buy' }"
            @click="direction = 'buy'"
          >
            {{ t('profile.economyBuy') }}
          </button>
          <button
            type="button"
            :class="{ 'is-active': direction === 'sell' }"
            @click="direction = 'sell'"
          >
            {{ t('profile.economySell') }}
          </button>
        </div>
        <label class="field">
          <span>{{ t('profile.economyYouPay') }}</span>
          <div class="sil-economy__input-wrap">
            <input
              v-model.number="amount"
              class="input"
              type="number"
              min="0.000001"
              step="any"
              inputmode="decimal"
              autocomplete="off"
              :aria-label="t('profile.economyYouPay')"
            />
            <strong>{{ direction === 'buy' ? 'SOL' : 'SIL' }}</strong>
          </div>
          <small>{{ t('profile.economyAvailable', { amount: availableLabel }) }}</small>
          <small v-if="direction === 'buy'">{{ t('profile.economySolFeeReserve') }}</small>
        </label>
        <div class="sil-economy__receive" aria-live="polite">
          <span>{{ t('profile.economyYouReceive') }}</span>
          <strong>{{
            quote
              ? `${number(quote.output, direction === 'buy' ? 4 : 6)} ${direction === 'buy' ? 'SIL' : 'SOL'}`
              : '—'
          }}</strong>
          <small v-if="quote">{{
            t('profile.economySwapDetails', {
              impact: `${quote.priceImpactPercent.toFixed(2)}%`,
              slippage: '0.50%',
            })
          }}</small>
          <small v-else>{{ t('profile.economyQuoteUnavailable') }}</small>
        </div>
        <UiButton type="submit" icon="wallet" :loading="swapLoading" :disabled="!canSwap">{{
          t('profile.economySwapButton')
        }}</UiButton>
        <UiNotice v-if="!walletAddress" tone="warning">{{
          t('profile.economyWalletRequired')
        }}</UiNotice>
        <UiNotice v-else-if="solBalance === null || solBalance < SOL_FEE_RESERVE" tone="warning">{{
          t('profile.economySolFeeReserve')
        }}</UiNotice>
        <UiNotice v-else-if="availableInputBalance === null" tone="warning">{{
          t('profile.economyBalanceUnavailable')
        }}</UiNotice>
        <UiNotice
          v-else-if="availableInputBalance !== null && amount > availableBalance"
          tone="warning"
          >{{ t('profile.economyInsufficient') }}</UiNotice
        >
        <UiNotice v-if="swapError" tone="danger">{{ swapErrorText }}</UiNotice>
        <UiNotice v-if="swapSignature" tone="success">
          {{ t('profile.economySwapComplete') }}
          <a
            :href="`https://explorer.solana.com/tx/${swapSignature}?cluster=devnet`"
            target="_blank"
            rel="noreferrer"
            >{{ t('profile.economyViewTransaction') }}</a
          >
        </UiNotice>
      </form>

      <div class="sil-economy__footer">
        <small>{{ t('profile.economyTestOnly') }}</small>
        <nav :aria-label="t('profile.economyLinks')">
          <a :href="poolExplorerUrl" target="_blank" rel="noreferrer">{{
            t('profile.economyViewPool')
          }}</a>
          <a href="https://faucet.solana.com" target="_blank" rel="noreferrer">{{
            t('profile.economyGetDevnetSol')
          }}</a>
        </nav>
      </div>
    </div>
  </UiCard>
</template>

<script setup lang="ts">
import { useSILEconomy } from '~/composables/useSILEconomy';

const props = defineProps<{
  walletAddress: string;
  solBalance: number | null;
  silBalance: number | null;
}>();
const emit = defineEmits<{ 'refresh-balances': [] }>();
const { t } = useI18n();
const { market, marketError, refreshMarket, quoteSwap, swap, swapLoading, swapError } =
  useSILEconomy();
const SOL_FEE_RESERVE = 0.01;
const direction = ref<'buy' | 'sell'>('buy');
const amount = ref(0.01);
const swapSignature = ref('');
const quote = computed(() => quoteSwap(amount.value, direction.value));
const availableInputBalance = computed(() =>
  direction.value === 'buy' ? props.solBalance : props.silBalance,
);
const availableBalance = computed(() =>
  direction.value === 'buy'
    ? Math.max((props.solBalance ?? 0) - SOL_FEE_RESERVE, 0)
    : (props.silBalance ?? 0),
);
const availableLabel = computed(() => {
  if (availableInputBalance.value === null) return direction.value === 'buy' ? '— SOL' : '— SIL';
  return direction.value === 'buy'
    ? `${availableBalance.value.toFixed(4)} SOL`
    : `${availableBalance.value.toFixed(2)} SIL`;
});
const swapErrorText = computed(() => {
  const message = swapError.value.toLowerCase();
  if (message.includes('install phantom')) return t('profile.economyPhantomRequired');
  if (message.includes('linked to this account')) return t('profile.economyWalletMismatch');
  if (message.includes('reject')) return t('profile.economySwapRejected');
  return message ? t('profile.economySwapFailed') : '';
});
const canSwap = computed(() =>
  Boolean(
    props.walletAddress &&
    quote.value &&
    amount.value > 0 &&
    availableInputBalance.value !== null &&
    amount.value <= availableBalance.value &&
    props.solBalance !== null &&
    props.solBalance >= SOL_FEE_RESERVE &&
    !swapLoading.value,
  ),
);
const poolExplorerUrl = computed(
  () =>
    `https://explorer.solana.com/address/${market.value?.poolId || '66Un5iGRBuzE4kcVQkDkKrtZUVnTiXnxpUHoFL3mEsdS'}?cluster=devnet`,
);

function number(value: number, maximumFractionDigits = 4): string {
  return value.toLocaleString(undefined, { maximumFractionDigits });
}

function usd(value: number): string {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumSignificantDigits: 5,
  }).format(value);
}

async function submitSwap() {
  swapSignature.value = '';
  try {
    swapSignature.value = await swap(amount.value, direction.value, props.walletAddress);
    emit('refresh-balances');
  } catch {
    // The composable keeps the provider and RPC error visible to the user.
  }
}

let marketTimer: ReturnType<typeof setInterval> | undefined;
onMounted(async () => {
  await refreshMarket();
  marketTimer = setInterval(() => {
    if (document.visibilityState === 'visible') refreshMarket(true);
  }, 30_000);
});
onBeforeUnmount(() => {
  if (marketTimer) clearInterval(marketTimer);
});
</script>

<style scoped>
.sil-economy {
  display: grid;
  gap: 1rem;
}
.sil-economy__market {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.7rem;
}
.sil-economy__price,
.sil-economy__rate,
.sil-economy__receive {
  display: grid;
  gap: 0.2rem;
  min-width: 0;
  padding: 0.85rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-soft);
}
.sil-economy__price span,
.sil-economy__rate span,
.sil-economy__receive span {
  color: var(--ink-600);
  font-size: 0.9375rem;
}
.sil-economy__price strong,
.sil-economy__rate strong,
.sil-economy__receive strong {
  color: var(--ink-950);
  font: 700 1.15rem/1.35 var(--font-mono);
  overflow-wrap: anywhere;
}
.sil-economy__price small,
.sil-economy__rate small,
.sil-economy__receive small {
  color: var(--ink-500);
  font-size: 0.9375rem;
  line-height: 1.4;
}
.sil-economy__basis {
  display: grid;
  gap: 0.35rem;
  padding: 0.8rem 0.9rem;
  border-left: 3px solid var(--mint-500);
  border-radius: 0.25rem var(--radius-md) var(--radius-md) 0.25rem;
  background: var(--mint-100);
}
.sil-economy__basis p {
  margin: 0;
  color: var(--ink-700);
  font-size: 0.9375rem;
  line-height: 1.5;
}
.sil-economy__swap {
  display: grid;
  gap: 0.8rem;
}
.sil-economy__directions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.25rem;
  padding: 0.25rem;
  border: 1px solid var(--border);
  border-radius: 0.8rem;
  background: var(--surface-soft);
}
.sil-economy__directions button {
  min-height: 2.6rem;
  border: 0;
  border-radius: 0.58rem;
  background: transparent;
  color: var(--ink-600);
  font: inherit;
  font-size: 1rem;
  font-weight: 750;
  cursor: pointer;
}
.sil-economy__directions button.is-active {
  background: white;
  color: var(--mint-800);
  box-shadow: var(--shadow-sm);
}
.sil-economy__input-wrap {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 0.5rem;
}
.sil-economy__input-wrap > strong {
  color: var(--ink-800);
  font: 700 1rem/1 var(--font-mono);
}
.sil-economy__swap .field small {
  color: var(--ink-500);
  font-size: 0.9375rem;
}
.sil-economy__footer {
  display: grid;
  gap: 0.6rem;
  padding-top: 0.8rem;
  border-top: 1px solid var(--border);
}
.sil-economy__footer small {
  color: var(--ink-500);
  font-size: 0.9375rem;
  line-height: 1.45;
}
.sil-economy__footer nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem 1rem;
}
.sil-economy__footer a,
.sil-economy__swap a {
  color: var(--mint-700);
  font-size: 0.9375rem;
  font-weight: 700;
  text-decoration: underline;
  text-underline-offset: 2px;
}
@media (max-width: 520px) {
  .sil-economy__market {
    grid-template-columns: 1fr;
  }
  .sil-economy__footer nav {
    display: grid;
  }
}
</style>
