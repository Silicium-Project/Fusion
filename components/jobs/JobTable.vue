<template>
  <div v-if="loading" class="job-table-loading"><div v-for="n in 5" :key="n" class="skeleton"></div></div>
  <UiEmptyState v-else-if="!jobs.length" title="Aucun projet dans cette vue" description="Les projets créés par votre compte apparaîtront ici. Modifiez les filtres ou lancez un nouveau calcul." icon="jobs" />
  <div v-else class="table-wrap">
    <table class="data-table">
      <thead><tr><th>Projet</th><th>Statut</th><th>Découpage</th><th>Création</th><th><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>
        <tr v-for="job in jobs" :key="job.id">
          <td><NuxtLink :to="`/jobs/${job.id}`" class="job-name"><span><UiIcon name="cube"/></span><div><strong>{{ job.title }}</strong><small>{{ job.workload }} · {{ compactIdentifier(job.siliciumJobId, 10, 5) }}</small></div></NuxtLink></td>
          <td><UiStatusBadge :status="job.status" /></td>
          <td><strong class="distribution">{{ fragmentCount(job) }}</strong><small class="cell-detail">parties</small></td>
          <td><span>{{ formatDate(job.createdAt) }}</span><small v-if="job.startedAt" class="cell-detail">{{ formatDuration(job.startedAt, job.completedAt) }}</small></td>
          <td><div class="row-actions"><UiButton :to="`/jobs/${job.id}`" variant="ghost" size="small" icon="chevron">Ouvrir</UiButton><button v-if="isJobCancellable(job.status)" type="button" class="icon-action icon-action--danger" :aria-label="`Annuler ${job.title}`" @click="$emit('cancel', job)"><UiIcon name="x"/></button><button v-if="job.status === 'completed'" type="button" class="icon-action" :aria-label="`Télécharger ${job.title}`" @click="$emit('download', job)"><UiIcon name="download"/></button></div></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type { Job } from '~/types/api';
import { compactIdentifier, formatDate, formatDuration } from '~/utils/format';
import { isJobCancellable } from '~/utils/jobs';
defineProps<{ jobs: Job[]; loading?: boolean }>();
defineEmits<{ cancel: [job: Job]; download: [job: Job] }>();
function fragmentCount(job: Job): number { const networkCount = Number(job.network?.total || 0); return Number(job.fragmentCount || networkCount || 0); }
</script>

<style scoped>
.job-table-loading{display:grid;gap:.65rem;padding:1rem}.job-table-loading .skeleton{height:3.8rem}.job-name{display:flex;min-width:220px;align-items:center;gap:.7rem}.job-name>span{display:grid;width:2rem;height:2rem;flex:0 0 auto;place-items:center;border-radius:.55rem;background:var(--violet-100);color:var(--violet-600)}.job-name svg{width:.9rem}.job-name strong,.job-name small{display:block}.job-name strong{font-size:.78rem}.job-name small{margin-top:.25rem;color:var(--ink-500);font-size:.63rem}.distribution{font-size:.82rem}.cell-detail{display:block;margin-top:.2rem;color:var(--ink-500);font-size:.6rem}.row-actions{display:flex;align-items:center;justify-content:flex-end;gap:.2rem}.icon-action{display:grid;width:2rem;height:2rem;place-items:center;border:0;border-radius:.55rem;background:transparent;color:var(--ink-600);cursor:pointer}.icon-action:hover{background:var(--ink-100);color:var(--ink-950)}.icon-action--danger:hover{background:var(--red-100);color:var(--red-600)}.icon-action svg{width:.9rem}
</style>
