<template>
  <div class="scene-issues" :class="`scene-issues--${tone}`" role="status">
    <div class="scene-issues__head">
      <span class="scene-issues__icon"><UiIcon :name="tone === 'ok' ? 'check' : 'alert'"/></span>
      <div>
        <strong>{{ title }}</strong>
        <small>{{ summaryText }}</small>
      </div>
      <UiButton v-if="editable" size="small" variant="secondary" icon="sparkle" @click="emit('open-editor')">{{ t('sceneCheck.openEditor') }}</UiButton>
    </div>
    <ul v-if="report.issues.length" class="scene-issues__list">
      <li v-for="(issue, index) in report.issues" :key="index" :class="`is-${issue.severity}`">
        <span class="scene-issues__line">{{ issue.line ? t('sceneCheck.line', { line: issue.line }) : t('sceneCheck.wholeScene') }}</span>
        <span>{{ t(`sceneCheck.codes.${issue.code}`, issue.params) }}<template v-if="issue.suggestion">{{ ` ${t('sceneCheck.suggestion', { suggestion: issue.suggestion })}` }}</template></span>
      </li>
    </ul>
    <p v-if="limits.length && !broken" class="scene-issues__hint">{{ t('sceneCheck.editorLimited', { what: limits.map((limit) => t(`sceneCheck.limits.${limit}`)).join(', ') }) }}</p>
    <p v-else-if="report.issues.length && editable" class="scene-issues__hint">{{ t('sceneCheck.openEditorHint') }}</p>
  </div>
</template>

<script setup lang="ts">
// Result of the check of an imported `.cfg` (utils/sceneCheck.ts): errors and
// warnings with their line, and a way to open the file in the scene editor
// when the editor can show everything the file uses (`limits` is empty).
import type { SceneReport } from '~/utils/sceneCheck';
import { sceneSummaryText } from '~/utils/jobs';

const props = withDefaults(defineProps<{ report: SceneReport; limits?: string[] }>(), { limits: () => [] });
const emit = defineEmits<{ 'open-editor': [] }>();
const { t } = useI18n();

/** Broken syntax: the editor cannot read the file. */
const broken = computed(() => props.report.issues.some((issue) => issue.code === 'syntax_error' || issue.code === 'unbalanced_braces'));
const editable = computed(() => !broken.value && !props.limits.length);
const tone = computed(() => (props.report.errors ? 'error' : props.report.warnings ? 'warning' : 'ok'));
const title = computed(() => {
  if (props.report.errors) return t('sceneCheck.errorsTitle', { count: props.report.errors });
  if (props.report.warnings) return t('sceneCheck.warningsTitle', { count: props.report.warnings });
  return t('sceneCheck.ok');
});
const summaryText = computed(() => sceneSummaryText(props.report.scene));
</script>

<style scoped>
.scene-issues{display:grid;gap:.7rem;padding:.9rem 1rem;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--green-100)}
.scene-issues--warning{border-color:rgba(166,89,20,.25);background:var(--amber-100)}.scene-issues--error{border-color:rgba(191,61,61,.28);background:var(--red-100)}
.scene-issues__head{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.75rem}
.scene-issues__head strong,.scene-issues__head small{display:block}.scene-issues__head strong{color:var(--ink-950);font-size:.9375rem}.scene-issues__head small{margin-top:.2rem;color:var(--ink-600);font-size:.9375rem}
.scene-issues__icon{display:grid;width:2.2rem;height:2.2rem;place-items:center;border-radius:.65rem;background:white;color:var(--green-600)}.scene-issues__icon svg{width:1rem}
.scene-issues--warning .scene-issues__icon{color:var(--amber-600)}.scene-issues--error .scene-issues__icon{color:var(--red-600)}
.scene-issues__list{display:grid;gap:.35rem;margin:0;padding:0;list-style:none}
.scene-issues__list li{display:grid;grid-template-columns:5.2rem 1fr;gap:.6rem;padding:.5rem .65rem;border-left:3px solid var(--amber-600);border-radius:.45rem;background:white;color:var(--ink-800);font-size:.9375rem;line-height:1.45}
.scene-issues__list li.is-error{border-left-color:var(--red-600)}
.scene-issues__line{color:var(--ink-500);font-family:var(--font-mono);font-size:.9375rem}
.scene-issues__hint{margin:0;color:var(--ink-600);font-size:.9375rem;line-height:1.45}
@media(max-width:620px){.scene-issues__head{grid-template-columns:auto 1fr}.scene-issues__head :deep(.ui-button){grid-column:1/-1}.scene-issues__list li{grid-template-columns:1fr;gap:.15rem}}
</style>
