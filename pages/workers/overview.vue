<template>
  <div class="app-page worker-overview">
    <header class="app-page-head">
      <div>
        <span class="eyebrow">{{ t('observability.worker.kicker') }}</span>
        <h1 class="page-title">{{ t('observability.worker.overviewTitle') }}</h1>
        <p class="page-intro">{{ t('observability.worker.overviewIntro') }}</p>
      </div>
      <UiButton to="/download" variant="secondary" icon="download">{{ t('observability.worker.install') }}</UiButton>
    </header>

    <section class="worker-account surface" :aria-label="t('observability.worker.accountTitle')">
      <div class="worker-account__identity">
        <span class="worker-account__avatar" aria-hidden="true">{{ accountInitials }}</span>
        <div>
          <span class="eyebrow">{{ t('observability.worker.accountTitle') }}</span>
          <h2>{{ accountName }}</h2>
          <p>{{ user?.email || '—' }}</p>
        </div>
      </div>
      <dl class="worker-account__facts">
        <div><dt>{{ t('observability.worker.accountRole') }}</dt><dd>{{ user?.role || t('profile.defaultRole') }}</dd></div>
        <div><dt>{{ t('observability.worker.accountSince') }}</dt><dd>{{ formatDate(user?.createdAt, false) }}</dd></div>
        <div><dt>{{ t('observability.worker.accountWallet') }}</dt><dd class="mono">{{ user?.walletAddress || '—' }}</dd></div>
        <div><dt>{{ t('observability.worker.accountSilBalance') }}</dt><dd>{{ silBalance === null ? '—' : `${silBalance.toFixed(2)} SIL` }}</dd></div>
      </dl>
      <p v-if="walletBalanceError" class="worker-account__balance-error">{{ walletBalanceError }}</p>
    </section>

    <section class="worker-devices surface" aria-labelledby="worker-devices-title">
      <div class="worker-section-head">
        <div>
          <span class="eyebrow">{{ t('observability.worker.deviceKicker') }}</span>
          <h2 id="worker-devices-title">{{ t('observability.worker.devicesTitle') }}</h2>
          <p>{{ t('observability.worker.devicesIntro') }}</p>
        </div>
        <div class="worker-section-head__actions">
          <UiButton variant="secondary" icon="refresh" :loading="devicesLoading" @click="loadDevices()">{{ t('observability.worker.refreshDevices') }}</UiButton>
          <UiButton v-if="isDevChannel" variant="secondary" icon="nodes" :loading="bulkPairingLoading" :disabled="!user?.walletAddress" @click="linkMiniworkers">{{ t('observability.worker.linkMiniworkers') }}</UiButton>
          <UiButton v-if="!isDevChannel" icon="plus" :loading="pairingLoading" :disabled="!user?.walletAddress" @click="generatePairingCode">{{ t('observability.worker.generateCode') }}</UiButton>
        </div>
      </div>

      <p v-if="!user?.walletAddress" class="worker-wallet-required">
        {{ t('observability.worker.walletRequired') }}
        <NuxtLink to="/profile">{{ t('observability.worker.openProfile') }}</NuxtLink>
      </p>
      <UiNotice v-if="deviceError" tone="danger">{{ deviceError }}</UiNotice>

      <div v-if="!isDevChannel && pairingCode" class="worker-pairing-code">
        <div>
          <strong>{{ t('observability.worker.pairingCodeTitle') }}</strong>
          <p>{{ t('observability.worker.pairingInstructions') }}</p>
        </div>
        <div class="worker-pairing-code__row">
          <code>{{ pairingCode }}</code>
          <UiButton variant="secondary" icon="copy" @click="copyPairingCode">{{ pairingCopied ? t('observability.worker.copied') : t('observability.worker.copyCode') }}</UiButton>
        </div>
        <small>{{ t('observability.worker.codeExpires', { time: formatDate(pairingExpiresAt) }) }}</small>
      </div>
      <div v-if="isDevChannel" class="worker-bulk-pairing">
        <div class="worker-bulk-pairing__head">
          <div><strong>{{ t('observability.worker.miniworkerCodesTitle') }}</strong><p>{{ t('observability.worker.miniworkerCodesText') }}</p></div>
        </div>
        <p class="worker-bulk-pairing__progress">{{ t('observability.worker.miniworkerProgress', { linked: linkedMiniworkerCount, total: 20 }) }}</p>
        <p class="worker-bulk-pairing__progress">{{ t('observability.worker.miniworkerNetworkProgress', { online: miniworkerOnlineCount, total: 20 }) }}</p>
        <p v-if="missingMiniworkerIds.length" class="worker-bulk-pairing__missing">{{ t('observability.worker.miniworkerMissing', { nodes: missingMiniworkerIds.join(', ') }) }}</p>
        <p class="worker-bulk-pairing__progress">{{ t('observability.worker.workerPayoutProofProgress', { ready: payoutProofDeviceCount, total: 20 }) }}</p>
        <p v-if="solanaPaymentsEnabled" class="worker-bulk-pairing__progress">{{ t('observability.worker.workerPayoutReadyProgress', { ready: payoutReadyCount, total: 20 }) }}</p>
        <p v-else class="worker-bulk-pairing__progress">{{ t('observability.worker.workerPayoutsDisabled') }}</p>
        <p v-if="solanaPaymentsEnabled && payoutProofDeviceCount > payoutReadyCount" class="worker-bulk-pairing__progress">{{ t('observability.worker.workerPayoutAuthorizationNote') }}</p>
        <UiButton v-if="solanaPaymentsEnabled && payoutProofDeviceCount > payoutReadyCount" variant="secondary" icon="wallet" :loading="payoutRegisterLoading" :disabled="!user?.walletAddress || payoutStatusLoading" @click="registerMiniworkerPayouts">{{ t('observability.worker.registerMiniworkerPayouts') }}</UiButton>
      </div>
      <UiNotice v-if="pairingMessage" :tone="pairingMessageTone">{{ pairingMessage }}</UiNotice>

      <div v-if="devices.length" class="worker-device-list" role="list" :aria-label="t('observability.worker.devicesTitle')">
        <article v-for="device in devices" :key="device.id" role="listitem" class="worker-device" :class="{ 'worker-device--selected': selectedDevice?.id === device.id }">
          <button class="worker-device__select" type="button" :aria-pressed="selectedDevice?.id === device.id" @click="selectDevice(device)">
            <span class="worker-device__heading">
              <strong class="mono">{{ device.nodeId }}</strong>
              <UiStatusBadge :status="deviceAvailability(device)" />
            </span>
            <span class="worker-device__meta">{{ t('observability.worker.linkedAt', { date: formatDate(device.linkedAt) }) }}</span>
            <span v-if="device.solanaWallet" class="worker-device__wallet mono">{{ t('observability.worker.workerWallet') }} · {{ compactIdentifier(device.solanaWallet, 9, 7) }}</span>
            <span v-if="device.payoutWallet" class="worker-device__wallet mono">{{ t('observability.worker.rewardWallet') }} · {{ compactIdentifier(device.payoutWallet, 9, 7) }}</span>
            <span class="worker-device__peer mono">{{ compactIdentifier(device.peerId, 12, 8) }}</span>
          </button>
          <UiButton variant="ghost" size="small" icon="close" :loading="unlinkingId === device.id" :aria-label="t('observability.worker.unlinkDevice', { node: device.nodeId })" @click="unlinkDevice(device)">{{ t('observability.worker.unlink') }}</UiButton>
        </article>
      </div>
      <UiEmptyState v-else-if="!devicesLoading && !deviceError" :title="t('observability.worker.noDevicesTitle')" :description="isDevChannel ? t('observability.worker.miniworkerCodesText') : t('observability.worker.noDevicesText')" icon="nodes">
        <UiButton v-if="isDevChannel" icon="nodes" :loading="bulkPairingLoading" :disabled="!user?.walletAddress" @click="linkMiniworkers">{{ t('observability.worker.linkMiniworkers') }}</UiButton>
        <UiButton v-else icon="plus" :loading="pairingLoading" :disabled="!user?.walletAddress" @click="generatePairingCode">{{ t('observability.worker.generateCode') }}</UiButton>
      </UiEmptyState>
    </section>

    <UiNotice v-if="error" tone="warning">{{ error }} {{ t('observability.telemetry.stale') }}</UiNotice>

    <template v-if="selectedDevice">
      <template v-if="selectedPeer">
        <UiNotice v-if="selectedPeer.online === false" tone="warning">{{ t('observability.worker.offline') }}</UiNotice>
        <section class="worker-summary surface" :aria-label="t('observability.worker.summary')">
          <div class="worker-summary__state">
            <UiStatusBadge :status="peerAvailability(selectedPeer)" />
            <strong class="mono">{{ selectedDevice.nodeId }}</strong>
            <span>{{ t('observability.telemetry.observed') }} · {{ observedAt }}</span>
          </div>
          <dl>
            <div v-for="item in summary" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div>
          </dl>
        </section>
        <section class="worker-chart surface">
          <TelemetryTrend :title="t('observability.telemetry.resources')" :samples="samples" />
          <p class="worker-chart__scope">{{ t('observability.telemetry.snapshot') }}</p>
        </section>
        <div class="worker-detail-grid">
          <UiCard :title="t('observability.worker.contribution')" padded>
            <dl class="worker-facts"><div v-for="item in contribution" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div></dl>
            <p class="worker-card-note">{{ t('observability.worker.counters') }}</p>
          </UiCard>
          <UiCard :title="t('observability.worker.configuration')" padded>
            <dl class="worker-facts">
              <div><dt>{{ t('observability.worker.roles') }}</dt><dd>{{ rolesLabel }}</dd></div>
              <div><dt>{{ t('observability.worker.version') }}</dt><dd class="mono">{{ selectedPeer.app_version || '—' }}</dd></div>
              <div><dt>{{ t('observability.worker.channel') }}</dt><dd>{{ selectedPeer.release_channel || '—' }}</dd></div>
              <div><dt>{{ t('observability.worker.uptime') }}</dt><dd>{{ uptime }}</dd></div>
            </dl>
            <UiButton v-if="selectedPeer.outdated" to="/download" variant="secondary" icon="download">{{ t('nodes.updateRequired') }}</UiButton>
          </UiCard>
        </div>
      </template>
      <UiCard v-else padded>
        <UiEmptyState :title="t('observability.worker.deviceNotReportingTitle')" :description="t('observability.worker.deviceNotReportingText')" icon="activity">
          <UiButton variant="secondary" icon="refresh" :loading="loading" @click="refreshNetwork">{{ t('common.refresh') }}</UiButton>
        </UiEmptyState>
      </UiCard>
    </template>
    <footer class="worker-overview__footer">
      <span>{{ t('observability.telemetry.poll', { seconds: 5 }) }}</span>
      <NuxtLink to="/nodes">{{ t('observability.worker.nodes') }}<UiIcon name="arrow" /></NuxtLink>
    </footer>
  </div>
</template>

<script setup lang="ts">
import type { Connection } from '@solana/web3.js';
import { compactIdentifier, formatDate, formatDuration, networkRoleGroup, peerAvailability, peerId, peerRoles } from '~/utils/format';
import { metricNumber, metricPercent, peerTelemetry, pendingTaskCount, publishedCount } from '~/utils/telemetry';
import { intlLocale } from '~/utils/i18n';
import { phantomProvider } from '~/utils/wallet';

definePageMeta({ layout: 'app', middleware: 'auth' });

interface UserDevice {
  id: number;
  userId: number;
  nodeId: string;
  peerId: string;
  solanaWallet?: string;
  payoutWallet?: string;
  workerPayoutProof?: { message: string; signature: string };
  linkedAt: string;
}

interface MiniworkerLinkResponse { nodeIds: string[]; count: number; expiresAt: string }
const miniworkerNodeIDPattern = /^miniworker-(0[1-9]|1[0-9]|2[0-4])$/;

const { t } = useI18n();
const route = useRoute();
const runtimeConfig = useRuntimeConfig();
const isDevChannel = computed(() => runtimeConfig.public.releaseChannel === 'dev');
const solanaPaymentsEnabled = computed(() => ['1', 'true', 'yes', 'on'].includes(
  String(runtimeConfig.public.solanaPaymentsEnabled ?? '').trim().toLowerCase(),
));
const { user, displayName, loadUser, authorizedFetch } = useSession();
const { silBalance, balanceError: walletBalanceError, loadBalance: loadWalletBalance } = useWallet();
const { peers, loading, error, lastUpdatedAt, loadNetwork } = useNetwork();
const devices = ref<UserDevice[]>([]);
const devicesLoading = ref(false);
const devicesRequestInFlight = ref(false);
const deviceError = ref('');
const pairingLoading = ref(false);
const pairingCode = ref('');
const pairingExpiresAt = ref('');
const pairingCopied = ref(false);
const pairingMessage = ref('');
const pairingMessageTone = ref<'success' | 'warning' | 'danger'>('success');
const bulkPairingLoading = ref(false);
const payoutRegisterLoading = ref(false);
const payoutStatusLoading = ref(false);
const payoutReadyIds = ref<string[]>([]);
const payoutStatusFingerprint = ref('');
const unlinkingId = ref<number | null>(null);
const selectedId = ref('');
const selectedDevice = computed(() => devices.value.find(device => device.nodeId === selectedId.value) || null);
const linkedMiniworkerCount = computed(() => devices.value.filter(device => miniworkerNodeIDPattern.test(device.nodeId)).length);
const payoutProofDeviceCount = computed(() => devices.value.filter(device =>
  miniworkerNodeIDPattern.test(device.nodeId) && Boolean(device.solanaWallet && device.payoutWallet && device.workerPayoutProof),
).length);
const payoutReadyCount = computed(() => payoutReadyIds.value.length);
const miniworkerOnlineCount = computed(() => peers.value.filter(peer => miniworkerNodeIDPattern.test(peerId(peer)) && peerAvailability(peer) === 'online').length);
const missingMiniworkerIds = computed(() => {
  const online = new Set(peers.value.filter(peer => miniworkerNodeIDPattern.test(peerId(peer)) && peerAvailability(peer) === 'online').map(peer => peerId(peer)));
  return Array.from({ length: 20 }, (_, index) => `miniworker-${String(index + 1).padStart(2, '0')}`).filter(nodeId => !online.has(nodeId));
});
const selectedPeer = computed(() => {
  if (!selectedDevice.value) return undefined;
  return peers.value.find(peer => peerId(peer) === selectedDevice.value?.nodeId || String(peer.peer_id || peer.peerId || '') === selectedDevice.value?.peerId);
});
const accountName = computed(() => {
  const fullName = [user.value?.firstName, user.value?.lastName].filter(Boolean).join(' ').trim();
  return fullName || displayName.value || '—';
});
const accountInitials = computed(() => accountName.value.split(/\s+/).slice(0, 2).map(part => part.charAt(0)).join('').toUpperCase() || 'S');
const runtime = computed(() => peerTelemetry(selectedPeer.value));
const fresh = computed(() => selectedPeer.value?.online === true && !error.value);
const number = (value: unknown) => {
  const n = metricNumber(value);
  return n === null ? '—' : new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 0 }).format(n);
};
const percent = (value: unknown) => {
  const n = metricPercent(value);
  return n === null ? '—' : new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 1 }).format(n) + ' %';
};
const summary = computed(() => [
  { label: t('observability.telemetry.cpu'), value: fresh.value ? percent(runtime.value?.system_cpu_percent) : '—' },
  { label: t('observability.telemetry.memory'), value: fresh.value ? percent(runtime.value?.system_memory_percent) : '—' },
  { label: t('observability.telemetry.active'), value: fresh.value ? number(publishedCount(selectedPeer.value?.activity?.active_tasks)) : '—' },
  { label: t('observability.telemetry.queue'), value: fresh.value ? number(pendingTaskCount(selectedPeer.value?.task_queue)) : '—' },
]);
const contribution = computed(() => [
  { label: t('observability.worker.handled'), value: number(selectedPeer.value?.metrics?.handled) },
  { label: t('observability.worker.failed'), value: number(selectedPeer.value?.metrics?.failed) },
  { label: t('observability.worker.retried'), value: number(selectedPeer.value?.metrics?.retried) },
]);
const observedAt = computed(() => formatDate(selectedPeer.value?.last_seen_utc || selectedPeer.value?.lastSeenUtc || lastUpdatedAt.value || undefined));
const rolesLabel = computed(() => peerRoles(selectedPeer.value || {}).map(role => {
  const group = networkRoleGroup(role);
  return group ? t('roles.' + group) : role;
}).join(', ') || '—');
const uptime = computed(() => {
  const seconds = metricNumber(runtime.value?.node_uptime_seconds);
  return seconds === null ? '—' : formatDuration(new Date(0).toISOString(), new Date(seconds * 1_000).toISOString());
});
const { samples, record, clear } = useTelemetryHistory();

function deviceAvailability(device: UserDevice): 'online' | 'offline' | 'unknown' {
  const peer = peers.value.find(item => peerId(item) === device.nodeId || String(item.peer_id || item.peerId || '') === device.peerId);
  return peer ? peerAvailability(peer) : 'unknown';
}

function selectDevice(device: UserDevice): void {
  selectedId.value = device.nodeId;
}

watch(selectedId, () => clear());

function apiMessage(error: unknown, fallback: string): string {
  const failure = error as { data?: { message?: string }; response?: { _data?: { message?: string } }; message?: string };
  return failure?.data?.message || failure?.response?._data?.message || failure?.message || fallback;
}

function isSolanaRpcRateLimited(failure: unknown): boolean {
  const error = failure as { message?: unknown; code?: unknown; cause?: { message?: unknown; code?: unknown } };
  return /SOLANA_RPC_RATE_LIMITED|429|too many requests|rate limit/i.test([
    error?.message,
    error?.code,
    error?.cause?.message,
    error?.cause?.code,
  ].filter(value => value !== undefined && value !== null).join(' '));
}

async function retrySolanaRpc<T>(operation: () => Promise<T>): Promise<T> {
  const delays = [500, 1_000, 2_000, 4_000];
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await operation();
    } catch (failure) {
      if (!isSolanaRpcRateLimited(failure)) throw failure;
      if (attempt >= delays.length) throw new Error('SOLANA_RPC_RATE_LIMITED');
      await new Promise(resolve => setTimeout(resolve, delays[attempt]! + Math.floor(Math.random() * 500)));
    }
  }
}

async function confirmWorkerPayoutBatch(connection: Connection, signatures: string[]): Promise<void> {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    const { value } = await retrySolanaRpc(() => connection.getSignatureStatuses(
      signatures,
      { searchTransactionHistory: true },
    ));
    let pending = false;
    value.forEach((status, index) => {
      if (status?.err) throw new Error(`Solana rejected worker payout transaction ${index + 1}.`);
      const confirmed = status && (
        status.confirmationStatus === 'confirmed'
        || status.confirmationStatus === 'finalized'
        || status.confirmations === null
      );
      if (!confirmed) pending = true;
    });
    if (!pending) return;
    await new Promise(resolve => setTimeout(resolve, 1_800 + Math.floor(Math.random() * 400)));
  }
  throw new Error('SOLANA_RPC_CONFIRMATION_PENDING');
}

async function loadDevices(background = false): Promise<void> {
  if (devicesRequestInFlight.value) return;
  devicesRequestInFlight.value = true;
  if (!background) {
    devicesLoading.value = true;
    deviceError.value = '';
  }
  try {
    const previousLinks = new Map(devices.value.map(device => [device.id, device.linkedAt]));
    const response = await authorizedFetch<{ items: UserDevice[] }>('/user/devices');
    deviceError.value = '';
    devices.value = Array.isArray(response.items) ? response.items : [];
    await refreshPayoutStatus(devices.value);
    if (!devices.value.some(device => device.nodeId === selectedId.value)) {
      const queryNode = typeof route.query.node === 'string' ? route.query.node : '';
      selectedId.value = devices.value.find(device => device.nodeId === queryNode)?.nodeId || devices.value[0]?.nodeId || '';
    }
    const linkedNow = devices.value.find(device => previousLinks.get(device.id) !== device.linkedAt);
    if (linkedNow && pairingCode.value) {
      pairingCode.value = '';
      pairingExpiresAt.value = '';
      pairingMessage.value = t('observability.worker.pairingComplete', { node: linkedNow.nodeId });
      pairingMessageTone.value = 'success';
    }
  } catch (failure) {
    deviceError.value = apiMessage(failure, t('observability.worker.devicesUnavailable'));
  } finally {
    devicesRequestInFlight.value = false;
    if (!background) devicesLoading.value = false;
  }
}

async function refreshPayoutStatus(targets: UserDevice[], force = false): Promise<void> {
  const walletAddress = user.value?.walletAddress;
  const runtime = useRuntimeConfig();
  const mint = String(runtime.public.silMint || '').trim();
  const eligible = targets.filter(device => miniworkerNodeIDPattern.test(device.nodeId) && device.solanaWallet && device.payoutWallet === walletAddress);
  if (!walletAddress || !mint || !eligible.length) {
    payoutReadyIds.value = [];
    payoutStatusFingerprint.value = '';
    return;
  }
  const fingerprint = `${walletAddress}:${eligible.map(device => `${device.nodeId}:${device.solanaWallet}`).sort().join('|')}`;
  if (!force && fingerprint === payoutStatusFingerprint.value) return;
  if (payoutStatusLoading.value) return;
  payoutStatusLoading.value = true;
  try {
    const [{ Connection }, { inspectWorkerPayouts }] = await Promise.all([
      import('@solana/web3.js'),
      import('~/utils/workerPayout'),
    ]);
    const connection = new Connection(String(runtime.public.solanaRpc), 'confirmed');
    payoutReadyIds.value = await inspectWorkerPayouts(connection, walletAddress, mint, eligible);
    payoutStatusFingerprint.value = fingerprint;
  } catch {
    payoutReadyIds.value = [];
  } finally {
    payoutStatusLoading.value = false;
  }
}

async function generatePairingCode(): Promise<void> {
  pairingLoading.value = true;
  pairingCode.value = '';
  pairingExpiresAt.value = '';
  pairingMessage.value = '';
  pairingCopied.value = false;
  try {
    const response = await authorizedFetch<{ code: string; expiresAt: string }>('/user/devices/pairing-code', { method: 'POST' });
    pairingCode.value = response.code;
    pairingExpiresAt.value = response.expiresAt;
  } catch (failure) {
    pairingMessageTone.value = 'danger';
    pairingMessage.value = apiMessage(failure, t('observability.worker.pairingFailed'));
  } finally {
    pairingLoading.value = false;
  }
}

async function linkMiniworkers(): Promise<void> {
  bulkPairingLoading.value = true;
  pairingMessage.value = '';
  const nodeIds = Array.from({ length: 20 }, (_, index) => `miniworker-${String(index + 1).padStart(2, '0')}`);
  try {
    const response = await authorizedFetch<MiniworkerLinkResponse>('/user/devices/pairing-codes', {
      method: 'POST',
      body: { nodeIds },
    });
    pairingMessageTone.value = 'success';
    pairingMessage.value = t('observability.worker.miniworkerCodesReady', { count: response.count || response.nodeIds?.length || 0 });
    await loadDevices(true);
  } catch (failure) {
    pairingMessageTone.value = 'danger';
    pairingMessage.value = apiMessage(failure, t('observability.worker.pairingFailed'));
  } finally {
    bulkPairingLoading.value = false;
  }
}

async function registerMiniworkerPayouts(): Promise<void> {
  if (!import.meta.client || !solanaPaymentsEnabled.value || !user.value?.walletAddress || payoutRegisterLoading.value) return;
  const targets = devices.value.filter(device =>
    miniworkerNodeIDPattern.test(device.nodeId) && device.solanaWallet && device.payoutWallet && device.workerPayoutProof,
  );
  if (!targets.length) return;
  payoutRegisterLoading.value = true;
  pairingMessage.value = '';
  try {
    const provider = phantomProvider(window);
    if (!provider?.signAllTransactions) {
      throw new Error('Phantom is required and must support signing the worker-link transactions as a group.');
    }
    const connected = await provider.connect();
    if (connected.publicKey.toString() !== user.value.walletAddress) {
      throw new Error(t('observability.worker.workerPayoutWalletMismatch'));
    }
    const config = useRuntimeConfig();
    const mint = String(config.public.silMint || '').trim();
    if (!mint) throw new Error(t('errors.walletBalanceUnavailable'));
    const [{ Connection }, { buildWorkerPayoutTransactions }] = await Promise.all([
      import('@solana/web3.js'),
      import('~/utils/workerPayout'),
    ]);
    const connection = new Connection(String(config.public.solanaRpc), 'confirmed');
    const built = await buildWorkerPayoutTransactions(connection, user.value.walletAddress, mint, targets);
    if (!built.transactions.length) {
      pairingMessageTone.value = 'success';
      pairingMessage.value = t('observability.worker.workerPayoutAlreadyLinked', { count: built.alreadyLinked });
      return;
    }
    pairingMessageTone.value = 'warning';
    pairingMessage.value = t('observability.worker.workerPayoutSubmitting', { count: built.transactions.length });
    const signed = await provider.signAllTransactions(built.transactions.map(item => item.transaction));
    if (signed.length !== built.transactions.length) throw new Error('Phantom returned an incomplete transaction batch.');
    const signatures: string[] = [];
    for (const [index, signedTransaction] of signed.entries()) {
      const signature = await retrySolanaRpc(() => connection.sendRawTransaction(
        signedTransaction.serialize(),
        { maxRetries: 3, preflightCommitment: 'confirmed' },
      ));
      signatures.push(signature);
    }
    await confirmWorkerPayoutBatch(connection, signatures);
    pairingMessageTone.value = 'success';
    pairingMessage.value = built.registered
      ? t('observability.worker.workerPayoutComplete', { count: built.registered, already: built.alreadyLinked })
      : t('observability.worker.workerPayoutAlreadyLinked', { count: built.alreadyLinked });
    payoutStatusFingerprint.value = '';
    await Promise.all([loadDevices(true), loadWalletBalance(user.value.walletAddress)]);
  } catch (failure) {
    pairingMessageTone.value = 'danger';
    const code = (failure as { message?: unknown })?.message;
    pairingMessage.value = isSolanaRpcRateLimited(failure)
      ? t('observability.worker.workerPayoutRpcLimited')
      : code === 'SOLANA_RPC_CONFIRMATION_PENDING'
        ? t('observability.worker.workerPayoutConfirmationPending')
        : apiMessage(failure, t('observability.worker.workerPayoutFailed'));
  } finally {
    payoutRegisterLoading.value = false;
  }
}

async function copyPairingCode(): Promise<void> {
  try {
    await navigator.clipboard.writeText(pairingCode.value);
    pairingCopied.value = true;
    pairingMessageTone.value = 'success';
    pairingMessage.value = t('observability.worker.codeCopied');
  } catch {
    pairingMessageTone.value = 'warning';
    pairingMessage.value = t('observability.worker.copyFailed');
  }
}

async function unlinkDevice(device: UserDevice): Promise<void> {
  if (!import.meta.client || !window.confirm(t('observability.worker.unlinkConfirm', { node: device.nodeId }))) return;
  unlinkingId.value = device.id;
  deviceError.value = '';
  try {
    await authorizedFetch('/user/devices/' + device.id, { method: 'DELETE' });
    await loadDevices();
  } catch (failure) {
    deviceError.value = apiMessage(failure, t('observability.worker.unlinkFailed'));
  } finally {
    unlinkingId.value = null;
  }
}

watch([selectedId, lastUpdatedAt], () => {
  if (!import.meta.client || !selectedPeer.value) return;
  const at = metricNumber(runtime.value?.sampled_unix);
  record({
    at: at !== null ? at * 1_000 : Date.parse(lastUpdatedAt.value || ''),
    cpu: fresh.value ? metricPercent(runtime.value?.system_cpu_percent) : null,
    memory: fresh.value ? metricPercent(runtime.value?.system_memory_percent) : null,
    queue: fresh.value ? pendingTaskCount(selectedPeer.value.task_queue) : null,
    active: fresh.value ? publishedCount(selectedPeer.value.activity?.active_tasks) : null,
  });
});

let timer: ReturnType<typeof setInterval> | undefined;
let devicesTimer: ReturnType<typeof setInterval> | undefined;
let walletTimer: ReturnType<typeof setInterval> | undefined;
let disposed = false;
async function refreshNetwork(): Promise<void> {
  if (!loading.value) await loadNetwork(true).catch(() => undefined);
}

onMounted(async () => {
  await Promise.all([loadUser().catch(() => undefined), loadDevices(), refreshNetwork()]);
  await loadWalletBalance(user.value?.walletAddress);
  await refreshPayoutStatus(devices.value, true);
  if (disposed) return;
  timer = setInterval(() => {
    if (document.visibilityState !== 'visible') return;
    refreshNetwork();
  }, 5_000);
  devicesTimer = setInterval(() => {
    if (document.visibilityState === 'visible') loadDevices(true);
  }, 10_000);
  walletTimer = setInterval(() => {
    if (document.visibilityState === 'visible') loadWalletBalance(user.value?.walletAddress);
  }, 30_000);
});

onBeforeUnmount(() => {
  disposed = true;
  if (timer) clearInterval(timer);
  if (devicesTimer) clearInterval(devicesTimer);
  if (walletTimer) clearInterval(walletTimer);
});

useSeoMeta({ title: () => t('observability.worker.nav') + ' — Silicium' });
</script>

<style scoped>
.worker-overview{gap:1.8rem}
.worker-account{display:grid;grid-template-columns:minmax(16rem,.8fr) minmax(0,1.5fr);align-items:center;gap:2rem;padding:1.6rem}
.worker-account__balance-error{grid-column:1/-1;margin:0;color:var(--warning-700,var(--ink-600));font-size:.9375rem;line-height:1.45}
.worker-account__identity{display:flex;align-items:center;gap:1rem;min-width:0}
.worker-account__avatar{display:grid;width:3.5rem;height:3.5rem;flex:0 0 auto;place-items:center;border:1px solid var(--glass-edge);border-radius:1.1rem;background:linear-gradient(145deg,rgba(255,255,255,.9),var(--mint-100));box-shadow:var(--glass-inset),var(--shadow-xs);color:var(--mint-700);font-size:1.2rem;font-weight:650}
.worker-account__identity h2,.worker-section-head h2{margin:.2rem 0;font-size:1.25rem;line-height:1.35;font-weight:620;letter-spacing:-.025em}
.worker-account__identity p,.worker-section-head p{margin:.3rem 0 0;color:var(--ink-600);font-size:1rem;line-height:1.6;overflow-wrap:anywhere}
.worker-account__facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem;margin:0}
.worker-account__facts>div{min-width:0;padding-left:1rem;border-left:1px solid var(--border)}
.worker-account__facts dt{color:var(--ink-600);font-size:1rem}
.worker-account__facts dd{margin:.4rem 0 0;color:var(--ink-950);font-size:1rem;font-weight:550;line-height:1.5;overflow-wrap:anywhere}
.worker-devices{display:grid;gap:1.25rem;padding:1.6rem}
.worker-section-head{display:flex;justify-content:space-between;align-items:center;gap:1.5rem}
.worker-section-head>div:first-child{max-width:45rem}
.worker-section-head__actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:.65rem}
.worker-pairing-code{display:grid;gap:.8rem;padding:1.1rem 1.2rem;border:1px solid rgba(20,142,126,.25);border-radius:var(--radius-md);background:linear-gradient(140deg,rgba(226,250,245,.8),rgba(255,255,255,.72));box-shadow:var(--glass-inset)}
.worker-pairing-code strong{font-size:1.05rem}
.worker-pairing-code p{margin:.35rem 0 0;color:var(--ink-700);font-size:1rem;line-height:1.6}
.worker-pairing-code__row{display:flex;align-items:center;gap:.8rem}
.worker-pairing-code code{min-width:0;flex:1;padding:.8rem .9rem;border:1px solid var(--border);border-radius:.6rem;background:rgba(255,255,255,.8);color:var(--ink-950);font-size:clamp(.82rem,1.4vw,1rem);line-height:1.5;overflow-wrap:anywhere;user-select:all}
.worker-pairing-code small{color:var(--ink-600);font-size:.9375rem}
.worker-device-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.8rem}
.worker-device{display:flex;align-items:center;gap:.5rem;min-width:0;padding:.45rem .55rem .45rem .85rem;border:1px solid var(--border);border-radius:.85rem;background:rgba(255,255,255,.56);transition:border-color .2s,background-color .2s,box-shadow .2s}
.worker-device--selected{border-color:rgba(24,137,125,.4);background:linear-gradient(140deg,rgba(235,251,247,.9),rgba(255,255,255,.8));box-shadow:0 4px 14px rgba(25,107,97,.07)}
.worker-device__select{display:grid;flex:1;min-width:0;gap:.45rem;padding:.5rem 0;border:0;background:none;text-align:left;cursor:pointer;color:inherit}
.worker-device__select:focus-visible{outline:2px solid var(--mint-600);outline-offset:3px;border-radius:.3rem}
.worker-device__heading{display:flex;align-items:center;justify-content:space-between;gap:.7rem;min-width:0}
.worker-device__heading strong{min-width:0;font-size:1rem;font-weight:550;overflow-wrap:anywhere}
.worker-device__meta,.worker-device__peer{color:var(--ink-600);font-size:.95rem;line-height:1.5}
.worker-device__peer{overflow-wrap:anywhere}
.worker-device__wallet{color:var(--ink-600);font-size:.88rem;line-height:1.5;overflow-wrap:anywhere}
.worker-wallet-required{margin:0;padding:.9rem 1rem;border:1px solid var(--border);border-radius:.8rem;color:var(--ink-700);font-size:1rem;line-height:1.6}
.worker-wallet-required a{color:var(--mint-700);font-weight:650;text-decoration:underline;text-underline-offset:.2em}
.worker-devices :deep(.empty-state h3){font-size:1.2rem}
.worker-summary{display:grid;grid-template-columns:minmax(180px,.75fr) minmax(0,2fr);align-items:center;gap:2rem;padding:1.7rem}.worker-summary__state{display:grid;justify-items:start;min-width:0;gap:.75rem}.worker-summary__state>strong{max-width:100%;overflow-wrap:anywhere;font-size:1rem;font-weight:500}.worker-summary__state>span{font-size:.9375rem;line-height:1.6;color:var(--ink-600)}.worker-summary dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,7rem),1fr));gap:1.5rem 1rem;margin:0}.worker-summary dl>div{min-width:0}.worker-summary dt{color:var(--ink-600);font-size:1rem;line-height:1.5}.worker-summary dd{margin:.65rem 0 0;font:500 clamp(1.5rem,2.2vw,2.2rem)/1.2 var(--font-mono);color:var(--ink-950)}
.worker-chart{padding:1.7rem}.worker-chart__scope{margin:1.3rem 0 0;padding-top:1rem;border-top:1px solid var(--border);font-size:.9375rem;line-height:1.7;color:var(--ink-600)}.worker-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1.5rem;align-items:start}.worker-facts{margin:0}.worker-facts>div{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,8rem),1fr));align-items:baseline;gap:.7rem 1.5rem;padding:.9rem 0;border-bottom:1px solid var(--border);font-size:1rem;line-height:1.6}.worker-facts>div:first-child{padding-top:0}.worker-facts>div:last-child{border-bottom:0}.worker-facts dt{overflow-wrap:anywhere;color:var(--ink-600)}.worker-facts dd{margin:0;text-align:right;overflow-wrap:anywhere;color:var(--ink-950);font-weight:500}.worker-card-note{margin:1.2rem 0 0;padding-top:1rem;border-top:1px solid var(--border);color:var(--ink-600);font-size:.9375rem;line-height:1.7}
.worker-overview__footer{display:flex;align-items:center;justify-content:space-between;gap:1rem;color:var(--ink-600);font-size:.9375rem}.worker-overview__footer a{display:inline-flex;align-items:center;gap:.7rem;min-height:2.75rem;color:var(--mint-700)}.worker-overview__footer svg{width:1rem}
@media(max-width:1050px){.worker-account{grid-template-columns:1fr}.worker-account__facts>div:first-child{padding-left:0;border:0}.worker-section-head{align-items:flex-start;flex-direction:column}.worker-section-head__actions{justify-content:flex-start}}
@media(max-width:850px){.worker-device-list{grid-template-columns:1fr}.worker-summary{grid-template-columns:1fr}.worker-summary__state{grid-template-columns:auto minmax(0,1fr);align-items:center}.worker-summary__state>span{grid-column:1/-1}.worker-summary dl>div:first-child{padding-left:0;border:0}}
@media(max-width:760px){.worker-detail-grid{grid-template-columns:1fr}.worker-summary{padding:1.3rem}.worker-summary dl{grid-template-columns:repeat(auto-fit,minmax(min(100%,7rem),1fr));gap:1.5rem 1rem}.worker-chart{padding:1.25rem}.worker-account,.worker-devices{padding:1.25rem}.worker-account__facts{grid-template-columns:1fr;gap:.8rem}.worker-account__facts>div{padding:.8rem 0 0;border-top:1px solid var(--border);border-left:0}.worker-account__facts>div:first-child{padding-top:0;border-top:0}.worker-pairing-code__row{align-items:stretch;flex-direction:column}.worker-pairing-code__row .ui-button{align-self:flex-start}}
@media(max-width:400px){.worker-summary__state{grid-template-columns:1fr}.worker-summary__state>strong{font-size:.9375rem}.worker-overview__footer{align-items:start;flex-direction:column}.worker-facts>div{grid-template-columns:repeat(auto-fit,minmax(min(100%,7rem),1fr));gap:.6rem}}
.worker-bulk-pairing{display:grid;gap:.8rem;margin-top:1rem;padding:1rem;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}.worker-bulk-pairing__head{display:flex;align-items:center;justify-content:space-between;gap:1rem}.worker-bulk-pairing__head p{margin:.25rem 0 0;color:var(--ink-600);font-size:1rem;line-height:1.5}.worker-bulk-pairing__progress{margin:0;color:var(--ink-900);font-size:1.05rem;font-weight:750;line-height:1.5}@media(max-width:620px){.worker-bulk-pairing__head{align-items:flex-start;flex-direction:column}}
</style>
