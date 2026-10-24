<template>
  <div v-if="loading" class="job-table-loading"><div v-for="n in 5" :key="n" class="skeleton"></div></div>
  <UiEmptyState v-else-if="!jobs.length" :title="t('jobs.table.emptyTitle')" :description="t('jobs.table.emptyText')" icon="jobs" />
  <div v-else class="table-wrap" :class="{ 'table-wrap--compact': compact }">
    <table class="data-table">
      <thead><tr><th>{{ t('jobs.table.project') }}</th><th>{{ t('jobs.table.status') }}</th><th>{{ t('jobs.table.split') }}</th><th>{{ t('jobs.table.created') }}</th><th><span class="sr-only">{{ t('jobs.table.actions') }}</span></th></tr></thead>
      <tbody>
        <tr v-for="job in jobs" :key="job.id">
          <td><NuxtLink :to="`/jobs/${job.id}`" class="job-name"><span><UiIcon :name="workloadView(job.workload).icon"/></span><div><strong :title="job.title">{{ job.title }}</strong><small>{{ workloadView(job.workload).label }} · {{ compactIdentifier(job.siliciumJobId, 10, 5) }}</small></div></NuxtLink></td>
          <td><UiStatusBadge :status="job.status" /></td>
          <td :data-label="t('jobs.table.split')"><template v-if="partCount(job)"><strong class="distribution">{{ partCount(job) }}</strong><small class="cell-detail">{{ t('jobs.table.parts') }}</small></template><template v-else-if="isDocumentSearchWorkload(job.workload)"><strong class="distribution">{{ t('jobs.table.auto') }}</strong><small class="cell-detail">{{ t('jobs.table.autoDetail') }}</small></template><strong v-else class="distribution">—</strong></td>
          <td :data-label="t('jobs.table.created')"><span>{{ formatDate(job.createdAt) }}</span><small v-if="job.startedAt" class="cell-detail">{{ formatDuration(job.startedAt, job.completedAt) }}</small></td>
          <td><div class="row-actions"><UiButton :to="`/jobs/${job.id}`" variant="ghost" size="small" icon="chevron">{{ t('common.open') }}</UiButton><button v-if="isJobCancellable(job.status)" type="button" class="icon-action icon-action--danger" :aria-label="t('jobs.table.cancel', { title: job.title })" @click="$emit('cancel', job)"><UiIcon name="x"/></button><button v-if="job.status === 'completed'" type="button" class="icon-action" :aria-label="t('jobs.table.download', { title: job.title })" @click="$emit('download', job)"><UiIcon name="download"/></button></div></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type { Job } from '~/types/api';
import { compactIdentifier, formatDate, formatDuration } from '~/utils/format';
import { isJobCancellable, jobPartCount } from '~/utils/jobs';
import { isDocumentSearchWorkload } from '~/utils/documents';
import { isBatchAIWorkload } from '~/utils/batchAI';
defineProps<{ jobs: Job[]; loading?: boolean; compact?: boolean }>();
defineEmits<{ cancel: [job: Job]; download: [job: Job] }>();
const { t } = useI18n();
function workloadView(workload: string) {
  if (isDocumentSearchWorkload(workload)) return { label: t('workloads.items.documents.name'), icon: 'search' };
  if (isBatchAIWorkload(workload)) return { label: t('workloads.items.batchAI.name'), icon: 'sparkle' };
  if (workload === 'raytracer') return { label: t('workloads.items.raytracer.name'), icon: 'cube' };
  if (workload === 'calcul/integrity/sha256') return { label: t('workloads.items.sha256.name'), icon: 'shield' };
  return { label: workload, icon: 'layers' };
}
const partCount = (job: Job): number => jobPartCount(job.fragmentCount, job.network?.total);
</script>

<style scoped>
.job-table-loading{display:grid;gap:.65rem;padding:1rem}.job-table-loading .skeleton{height:3.8rem}.job-name{display:flex;min-width:220px;align-items:center;gap:.7rem}.job-name>span{display:grid;width:2rem;height:2rem;flex:0 0 auto;place-items:center;border-radius:.55rem;background:var(--violet-100);color:var(--violet-600)}.job-name svg{width:.9rem}.job-name>div{min-width:0}.job-name strong,.job-name small{display:block}.job-name strong{max-width:min(36vw,26rem);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.job-name strong{font-size:.9375rem}.job-name small{margin-top:.25rem;color:var(--ink-500);font-size:.9375rem}.distribution{font-size:.939rem}.cell-detail{display:block;margin-top:.2rem;color:var(--ink-500);font-size:.9375rem}.row-actions{display:flex;align-items:center;justify-content:flex-end;gap:.2rem}.icon-action{display:grid;width:2rem;height:2rem;place-items:center;border:0;border-radius:.55rem;background:transparent;color:var(--ink-600);cursor:pointer}.icon-action:hover{background:var(--ink-100);color:var(--ink-950)}.icon-action--danger:hover{background:var(--red-100);color:var(--red-600)}.icon-action svg{width:.9rem}


.table-wrap--compact{overflow:visible}.table-wrap--compact .data-table{display:block;min-width:0}.table-wrap--compact thead{display:none}.table-wrap--compact tbody{display:grid}.table-wrap--compact tbody tr{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:.75rem 1.1rem;padding:1.35rem 1.5rem;border-bottom:1px solid var(--border)}.table-wrap--compact tbody tr:last-child{border-bottom:0}.table-wrap--compact td{display:block;min-width:0;padding:0;border:0}.table-wrap--compact td:first-child{grid-column:1;grid-row:1}.table-wrap--compact td:nth-child(2){grid-column:2;grid-row:1;text-align:right}.table-wrap--compact td:nth-child(3){display:none}.table-wrap--compact td:nth-child(4){grid-column:1;grid-row:2;font-size:.9375rem;color:var(--ink-500)}.table-wrap--compact td:nth-child(4) .cell-detail{display:inline;margin-left:.65rem;font-size:.9375rem}.table-wrap--compact td:nth-child(5){grid-column:2;grid-row:2}.table-wrap--compact .job-name{min-width:0}.table-wrap--compact .job-name>div{min-width:0}.table-wrap--compact .job-name strong{max-width:100%}.table-wrap--compact .job-name small{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.9375rem}

@media(max-width:640px){
.table-wrap{overflow:visible}.data-table{display:block;min-width:0}.data-table thead{display:none}.data-table tbody{display:grid}.data-table tbody tr{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:.8rem 1rem;padding:1.15rem;border-bottom:1px solid var(--border)}.data-table tbody tr:last-child{border-bottom:0}.data-table td{display:block;min-width:0;padding:0;border:0;font-size:.9375rem}.data-table td:first-child{grid-column:1/-1}.data-table td:nth-child(3){text-align:right}.data-table td:nth-child(3)::before,.data-table td:nth-child(4)::before{display:block;margin-bottom:.3rem;color:var(--ink-500);font-size:.9375rem;content:attr(data-label)}.job-name{min-width:0}.job-name>div{min-width:0;flex:1}.job-name strong{max-width:100%;font-size:.95rem}.job-name small{overflow-wrap:anywhere;font-size:.9375rem;line-height:1.6}.row-actions{gap:.15rem}.icon-action{width:2.75rem;height:2.75rem}.row-actions :deep(.ui-button){padding:.6rem;font-size:.9375rem}.cell-detail{font-size:.9375rem}.distribution{font-size:.9375rem}
}
@media(max-width:640px){.table-wrap--compact td:nth-child(2){grid-column:1;grid-row:2;text-align:left}.table-wrap--compact td:nth-child(4){grid-column:1;grid-row:3}.table-wrap--compact td:nth-child(5){grid-column:2;grid-row:3}.table-wrap--compact tbody tr{padding:1.1rem}}
</style>
