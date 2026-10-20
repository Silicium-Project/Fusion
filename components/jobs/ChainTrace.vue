<template>
  <div class="chain-trace">
    <div class="chain-trace__status">
      <UiStatusBadge :label="statusText" :tone="statusTone" />
      <p>{{ statusDetail }}</p>
    </div>

    <UiNotice v-if="trace.status === 'failed' && trace.error" tone="danger" :title="t('chainTrace.failedTitle')">{{ trace.error }}</UiNotice>

    <dl v-if="signature || trace.merkleRoot" class="chain-trace__facts">
      <div v-if="signature"><dt>{{ t('chainTrace.transaction') }}</dt><dd><a :href="explorerUrl" target="_blank" rel="noopener noreferrer" class="mono">{{ compactIdentifier(signature, 12, 10) }}<UiIcon name="external" /></a></dd></div>
      <div v-if="trace.merkleRoot"><dt>{{ t('chainTrace.root') }}</dt><dd class="mono">{{ trace.merkleRoot }}</dd></div>
      <div v-if="trace.finalSha256"><dt>{{ t('chainTrace.final') }}</dt><dd class="mono">{{ trace.finalSha256 }}</dd></div>
      <div v-if="trace.payer"><dt>{{ t('chainTrace.payer') }}</dt><dd class="mono">{{ trace.payer }}</dd></div>
      <div v-if="trace.cluster"><dt>{{ t('chainTrace.cluster') }}</dt><dd>{{ trace.cluster }}</dd></div>
    </dl>

    <div v-if="tasks.length" class="chain-trace__check">
      <UiButton icon="shield" size="small" variant="secondary" :loading="checking" @click="check">{{ t('chainTrace.check') }}</UiButton>
      <p v-if="!result">{{ t('chainTrace.checkText') }}</p>
      <UiNotice v-else :tone="resultTone" :title="resultTitle">{{ resultText }}</UiNotice>
    </div>

    <div v-if="tasks.length" class="table-wrap">
      <table class="data-table chain-trace__tasks">
        <thead><tr><th>{{ t('chainTrace.task') }}</th><th>{{ t('chainTrace.worker') }}</th><th>{{ t('chainTrace.verification') }}</th><th>{{ t('chainTrace.result') }}</th><th>{{ t('chainTrace.proof') }}</th></tr></thead>
        <tbody>
          <tr v-for="task in visibleTasks" :key="task.task_id">
            <td class="mono" :title="task.task_id">#{{ task.fragment_index }}</td>
            <td class="mono" :title="task.worker">{{ compactIdentifier(task.worker || '—', 8, 6) }}</td>
            <td :title="verifierTitle(task)">{{ verificationLabel(task) }}</td>
            <td class="mono" :title="task.result_sha256">{{ compactIdentifier(task.result_sha256 || '—', 8, 6) }}</td>
            <td><span class="chain-trace__mark" :class="markClass(task)">{{ markLabel(task) }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <small v-if="tasks.length > visibleTasks.length" class="chain-trace__more">{{ t('chainTrace.more', { shown: visibleTasks.length, total: tasks.length }) }}</small>
  </div>
</template>

<script setup lang="ts">
// Blockchain trace of a job: where it was anchored, every task with who
// computed and verified it, and a check run in the browser that compares the
// Merkle root on Solana with the tasks shown here (see utils/chainProof).
import type { ChainTask, ChainTrace } from '~/types/api';
import { compactIdentifier } from '~/utils/format';
import { checkTrace, explorerTransactionUrl, fetchOnChainMemo, type TraceCheck } from '~/utils/chainProof';

const props = defineProps<{ trace: ChainTrace }>();
const { t } = useI18n();
const config = useRuntimeConfig();
const checking = ref(false);
const result = ref<TraceCheck | null>(null);
const visibleLimit = 60;

const tasks = computed<ChainTask[]>(() => (Array.isArray(props.trace.fragments) ? props.trace.fragments : []));
const visibleTasks = computed(() => tasks.value.slice(0, visibleLimit));
const signature = computed(() => props.trace.signatures?.[0] || '');
// Traces written before the cluster was recorded were all on devnet.
const explorerUrl = computed(() => props.trace.explorerUrl || explorerTransactionUrl(signature.value, props.trace.cluster || 'devnet'));

const statusTone = computed(() => ({ anchored: 'success', pending: 'warning', failed: 'danger' } as const)[props.trace.status as 'anchored'] || 'neutral');
const statusText = computed(() => {
  const key = ['anchored', 'pending', 'failed'].includes(String(props.trace.status)) ? String(props.trace.status) : 'disabled';
  return t(`chainTrace.status.${key}`);
});
const statusDetail = computed(() => {
  if (props.trace.status === 'anchored') return t('chainTrace.anchoredText', { count: tasks.value.length });
  if (props.trace.status === 'pending') return t('chainTrace.pendingText');
  if (props.trace.status === 'failed') return t('chainTrace.failedText');
  return props.trace.enabled ? t('chainTrace.waitingText') : t('chainTrace.disabledText');
});

const resultTone = computed(() => {
  if (!result.value) return 'info';
  const allValid = Object.values(result.value.tasks).every(Boolean);
  if (!allValid || result.value.chain === 'mismatch') return 'danger';
  return result.value.chain === 'match' ? 'success' : 'warning';
});
const resultTitle = computed(() => t(`chainTrace.outcome.${resultTone.value === 'success' ? 'ok' : resultTone.value === 'danger' ? 'broken' : 'partial'}`));
const resultText = computed(() => {
  if (!result.value) return '';
  const invalid = Object.values(result.value.tasks).filter((valid) => !valid).length;
  if (invalid) return t('chainTrace.outcome.invalidTasks', { count: invalid });
  if (result.value.chain === 'mismatch') return t('chainTrace.outcome.mismatch');
  if (result.value.chain === 'unreachable') return t('chainTrace.outcome.unreachable', { count: tasks.value.length });
  return t('chainTrace.outcome.match', { count: tasks.value.length });
});

function verifierTitle(task: ChainTask) {
  return (task.verifiers || []).map((verifier) => `${verifier.author} · ${verifier.verdict === true ? '✓' : verifier.verdict === false ? '✗' : '…'}`).join('\n');
}
function verificationLabel(task: ChainTask) {
  const verifiers = task.verifiers || [];
  if (!verifiers.length) return '—';
  if (verifiers.every((verifier) => verifier.self_verification)) return t('chainTrace.selfVerified');
  const approved = verifiers.filter((verifier) => verifier.verdict === true).length;
  return t('chainTrace.approvals', { count: approved, total: verifiers.length });
}
function markClass(task: ChainTask) {
  const valid = result.value?.tasks[task.task_id];
  return valid === undefined ? '' : valid ? 'is-valid' : 'is-invalid';
}
function markLabel(task: ChainTask) {
  const valid = result.value?.tasks[task.task_id];
  return valid === undefined ? '—' : valid ? t('chainTrace.valid') : t('chainTrace.invalid');
}

async function check() {
  if (!props.trace.merkleRoot) return;
  checking.value = true;
  try {
    result.value = await checkTrace(
      { tasks: tasks.value, root: props.trace.merkleRoot, finalSha256: String(props.trace.finalSha256 || '') },
      () => (signature.value && props.trace.status === 'anchored' ? fetchOnChainMemo(signature.value, String(config.public.solanaRpc)) : Promise.resolve(null)),
    );
  } finally {
    checking.value = false;
  }
}
</script>

<style scoped>
.chain-trace{display:grid;gap:1rem}.chain-trace__status{display:flex;align-items:center;gap:.75rem;flex-wrap:wrap}.chain-trace__status p,.chain-trace__check p{margin:0;color:var(--ink-600);font-size:1rem;line-height:1.55}
.chain-trace__facts{display:grid;margin:0;border:1px solid var(--border);border-radius:var(--radius-md)}.chain-trace__facts>div{display:grid;grid-template-columns:minmax(120px,.35fr) minmax(0,1fr);gap:1rem;padding:.65rem .9rem;border-bottom:1px solid var(--border)}.chain-trace__facts>div:last-child{border:0}.chain-trace__facts dt{color:var(--ink-500);font-size:.9375rem}.chain-trace__facts dd{margin:0;overflow-wrap:anywhere;color:var(--ink-800);font-size:.9375rem;font-weight:650}.chain-trace__facts a{display:inline-flex;align-items:center;gap:.4rem;color:var(--mint-700)}.chain-trace__facts svg{width:.8rem}
.chain-trace__check{display:grid;justify-items:start;gap:.6rem}.chain-trace__tasks{min-width:560px}.chain-trace__mark{font-size:.9375rem;font-weight:800;color:var(--ink-500)}.chain-trace__mark.is-valid{color:var(--green-600)}.chain-trace__mark.is-invalid{color:var(--red-600)}.chain-trace__more{color:var(--ink-500);font-size:.9375rem}
@media(max-width:560px){.chain-trace__facts>div{grid-template-columns:1fr;gap:.25rem}}
</style>
