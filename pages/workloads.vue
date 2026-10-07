<template>
  <div class="app-page workloads-page">
    <header class="app-page-head"><div><span class="eyebrow">{{ t('workloads.eyebrow') }}</span><h1 class="page-title">{{ t('workloads.title') }}</h1><p class="page-intro">{{ t('workloads.intro') }}</p></div><UiButton to="/jobs/new" icon="upload">{{ t('common.newJob') }}</UiButton></header>

    <section class="workloads-common surface" aria-labelledby="workloads-common-title">
      <h2 id="workloads-common-title">{{ t('workloads.commonTitle') }}</h2>
      <ol>
        <li v-for="(stage, index) in common" :key="index"><span>{{ index + 1 }}</span><div><strong>{{ stage.title }}</strong><p>{{ stage.text }}</p></div></li>
      </ol>
    </section>

    <nav class="workloads-toc" :aria-label="t('workloads.toc')">
      <a v-for="workload in workloads" :key="workload.key" :href="`#${workload.key}`"><span class="workloads-toc__icon"><UiIcon :name="workload.icon" /></span><span><strong>{{ workload.name }}</strong><small>{{ workload.tagline }}</small></span><UiIcon name="chevron" /></a>
    </nav>

    <article v-for="workload in workloads" :id="workload.key" :key="workload.key" class="workload surface" :aria-labelledby="`${workload.key}-title`">
      <header class="workload__head">
        <span class="workload__icon"><UiIcon :name="workload.icon" /></span>
        <div><h2 :id="`${workload.key}-title`">{{ workload.name }}</h2><p>{{ workload.tagline }}</p></div>
      </header>
      <div class="workload__body">
        <div class="workload__text">
          <section><h3>{{ t('workloads.purpose') }}</h3><p>{{ workload.purpose }}</p></section>
          <section><h3>{{ t('workloads.how') }}</h3><ol class="workload__steps"><li v-for="(line, index) in workload.how" :key="index">{{ line }}</li></ol></section>
          <section><h3>{{ t('workloads.give') }}</h3><p>{{ workload.give }}</p></section>
          <section><h3>{{ t('workloads.get') }}</h3><p>{{ workload.get }}</p></section>
          <section class="workload__limits"><h3>{{ t('workloads.limits') }}</h3><p>{{ workload.limits }}</p></section>
        </div>
        <aside class="workload__aside">
          <div class="workload__example">
            <span class="eyebrow">{{ t('workloads.example') }}</span>
            <strong class="mono">{{ workload.example.file }}</strong>
            <p>{{ workload.exampleText }}</p>
            <UiButton :href="`/examples/${workload.example.file}`" :download="workload.example.file" variant="secondary" size="small" icon="download">{{ t('workloads.downloadExample') }}</UiButton>
          </div>
          <dl class="workload__meta"><dt>{{ t('workloads.identifier') }}</dt><dd class="mono">{{ workload.id }}</dd></dl>
          <UiButton :to="{ path: '/jobs/new', query: { workload: workload.query } }" icon="arrow" size="small">{{ t('workloads.tryIt') }}</UiButton>
        </aside>
      </div>
    </article>
  </div>
</template>

<script setup lang="ts">
// "Types de calcul": what each workload of the Rust node is for, how it is
// split, computed and verified, what to give it, and an example file
// (served from `public/examples/`).
import { DOCUMENT_SEARCH_WORKLOAD } from '~/utils/documents';

definePageMeta({ layout: 'app', middleware: 'auth' });
const { t, tl } = useI18n();

/** The workloads, in the order of the job form. `query` preselects it there. */
const WORKLOADS = [
  { key: 'raytracer', id: 'raytracer', query: 'raytracer', icon: 'cube', example: { file: 'silicium-demo-scene.cfg' } },
  { key: 'sha256', id: 'calcul/integrity/sha256', query: 'calcul/integrity/sha256', icon: 'shield', example: { file: 'silicium-hash-example.txt' } },
  { key: 'documents', id: DOCUMENT_SEARCH_WORKLOAD, query: 'documents', icon: 'search', example: { file: 'silicium-documents-example.zip' } },
];

const common = computed(() => tl<{ title: string; text: string }>('workloads.common'));
const workloads = computed(() => WORKLOADS.map(workload => {
  const key = `workloads.items.${workload.key}`;
  return {
    ...workload,
    name: t(`${key}.name`), tagline: t(`${key}.tagline`), purpose: t(`${key}.purpose`), how: tl(`${key}.how`),
    give: t(`${key}.give`), get: t(`${key}.get`), limits: t(`${key}.limits`), exampleText: t(`${key}.exampleText`),
  };
}));

useSeoMeta({ title: () => t('workloads.seoTitle') });
</script>

<style scoped>
.workloads-page{display:grid;gap:1.1rem}
.workloads-common{padding:1.1rem 1.2rem}.workloads-common h2{margin:0 0 .85rem;color:var(--ink-900);font-size:.86rem;letter-spacing:-.02em}.workloads-common ol{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.8rem;margin:0;padding:0;list-style:none}.workloads-common li{display:grid;grid-template-columns:1.8rem 1fr;gap:.6rem}.workloads-common li>span{display:grid;width:1.8rem;height:1.8rem;place-items:center;border-radius:.5rem;background:var(--mint-100);color:var(--mint-700);font-size:.62rem;font-weight:850}.workloads-common strong{display:block;color:var(--ink-900);font-size:.7rem}.workloads-common p{margin:.25rem 0 0;color:var(--ink-600);font-size:.62rem;line-height:1.5}
.workloads-toc{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.7rem}.workloads-toc a{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.7rem;padding:.85rem .95rem;border:1px solid var(--border);border-radius:var(--radius-md);background:rgba(255,255,255,.7);transition:border-color .2s,transform .25s var(--ease-spring)}.workloads-toc a:hover{border-color:var(--mint-500);transform:translateY(-2px)}.workloads-toc__icon{display:grid;width:2.2rem;height:2.2rem;place-items:center;border-radius:.65rem;background:var(--mint-100);color:var(--mint-700)}.workloads-toc__icon svg{width:1rem}.workloads-toc strong,.workloads-toc small{display:block}.workloads-toc strong{color:var(--ink-900);font-size:.72rem}.workloads-toc small{margin-top:.2rem;color:var(--ink-500);font-size:.6rem;line-height:1.4}.workloads-toc a>svg{width:.8rem;color:var(--ink-400)}
.workload{scroll-margin-top:6.5rem;padding:1.3rem 1.4rem}.workload__head{display:flex;align-items:center;gap:.85rem;padding-bottom:1rem;border-bottom:1px solid var(--border)}.workload__icon{display:grid;flex:none;width:2.7rem;height:2.7rem;place-items:center;border-radius:.8rem;background:linear-gradient(145deg,var(--ink-800),var(--ink-950));color:white}.workload__icon svg{width:1.15rem}.workload__head h2{margin:0;color:var(--ink-950);font-size:1.15rem;letter-spacing:-.04em}.workload__head p{margin:.25rem 0 0;color:var(--ink-600);font-size:.7rem}
.workload__body{display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,280px);gap:1.4rem;padding-top:1.1rem}.workload__text{display:grid;gap:1rem}.workload__text h3{margin:0 0 .35rem;color:var(--ink-900);font-size:.7rem;font-weight:800;letter-spacing:.02em}.workload__text p{margin:0;color:var(--ink-700);font-size:.68rem;line-height:1.65}.workload__steps{display:grid;gap:.4rem;margin:0;padding-left:1.1rem;color:var(--ink-700);font-size:.68rem;line-height:1.6}.workload__steps li::marker{color:var(--mint-700);font-weight:800}.workload__limits{padding:.75rem .85rem;border:1px solid rgba(217,119,6,.22);border-radius:var(--radius-md);background:#fff8eb}
.workload__aside{display:grid;align-content:start;gap:.8rem}.workload__example{display:grid;gap:.45rem;padding:.95rem;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}.workload__example strong{overflow:hidden;color:var(--ink-900);font-size:.66rem;text-overflow:ellipsis;white-space:nowrap}.workload__example p{margin:0;color:var(--ink-600);font-size:.62rem;line-height:1.55}.workload__example :deep(.ui-button){justify-self:start;margin-top:.2rem}.workload__meta{margin:0;font-size:.6rem}.workload__meta dt{color:var(--ink-500)}.workload__meta dd{margin:.2rem 0 0;overflow-wrap:anywhere;color:var(--ink-800)}.workload__aside>:deep(.ui-button){justify-self:start}
@media(max-width:1100px){.workloads-common ol{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:860px){.workloads-toc{grid-template-columns:1fr}.workload__body{grid-template-columns:1fr}}
@media(max-width:560px){.workloads-common ol{grid-template-columns:1fr}.workload{padding:1rem}}
</style>
