<template>
  <div class="repository-installer" data-testid="repository-installer">
    <div class="repository-installer__head">
      <div class="repo-options" role="group" :aria-label="t('experience.repos.manager')">
        <button v-for="item in managers" :key="item" type="button" :aria-pressed="manager === item" :class="{ 'is-active': manager === item }" @click="manager = item">
          <span>{{ item.toUpperCase() }}</span>{{ t('experience.repos.' + item) }}
        </button>
      </div>
      <span class="repository-installer__signed"><UiIcon name="shield" />{{ t(manager === 'apt' ? 'experience.repos.aptSigned' : 'experience.repos.signed') }}</span>
    </div>
    <aside v-if="channel === 'dev'" class="repository-installer__prerequisite" data-testid="dev-prerequisites">
      <UiIcon name="network" />
      <div><strong>{{ t('experience.repos.devTitle') }}</strong><p>{{ t('experience.repos.devText') }}</p>
        <details><summary>{{ t('experience.repos.caTitle') }}</summary><p>{{ t('experience.repos.caText') }}</p><CommandSnippet :title="t('experience.repos.caCode')" :code="commands.ca" compact /></details>
      </div>
    </aside>
    <div class="repository-installer__step">
      <div class="repository-installer__label"><h3>{{ t('experience.repos.once') }}</h3><span>{{ t('experience.repos.onceHint') }}</span></div>
      <CommandSnippet :title="manager.toUpperCase() + ' · ' + channelLabel" :code="commands.setup" />
    </div>
    <div class="repository-installer__step">
      <h3>{{ t('experience.repos.install') }}</h3>
      <CommandSnippet :title="'silicium-node · ' + channelLabel" :code="commands.install" compact />
    </div>
    <p class="repository-installer__note"><UiIcon name="layers" />{{ t('experience.repos.chooseOne') }}</p>
    <details class="repository-installer__details">
      <summary>{{ t('experience.repos.update') }}</summary>
      <CommandSnippet :title="t('experience.repos.update')" :code="commands.update" compact />
    </details>
    <details class="repository-installer__details">
      <summary>{{ t('experience.repos.trouble') }}</summary>
      <p>{{ t('experience.repos.troubleText') }}</p>
      <CommandSnippet :title="t('experience.repos.diagnostic')" :code="commands.diagnose" compact />
    </details>
  </div>
</template>

<script setup lang="ts">
import { repositoryCommands, type PackageChannel, type PackageManager } from '~/utils/packageRepositories';
const props = defineProps<{ channel: PackageChannel; initialManager?: PackageManager }>();
const { t } = useI18n();
const managers: PackageManager[] = ['apt', 'dnf'];
const manager = ref<PackageManager>(props.initialManager || 'apt');
const commands = computed(() => repositoryCommands(manager.value, props.channel));
const channelLabel = computed(() => t('experience.download.' + (props.channel === 'prod' ? 'stable' : 'dev')));
</script>

<style scoped>
.repository-installer{display:grid;grid-template-columns:minmax(0,1fr);gap:1.75rem;min-width:0}.repository-installer__step{min-width:0}
.repository-installer__head{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}.repo-options{display:flex;gap:.5rem;flex-wrap:wrap}
.repo-options button{display:grid;gap:.3rem;min-width:11rem;min-height:3.5rem;padding:.8rem 1rem;border:1px solid var(--border);border-radius:.7rem;background:var(--surface-glass);color:var(--ink-600);text-align:left;font-size:.9375rem;cursor:pointer}.repo-options button>span{font-size:.9375rem;font-weight:600;color:var(--ink-900)}
.repo-options button.is-active{border-color:#94bdf0;background:linear-gradient(#fafdff,#edf5ff);box-shadow:inset 0 1px 0 #fff}
.repository-installer__signed{display:inline-flex;align-items:center;gap:.4rem;max-width:14rem;color:var(--ink-600);font-size:.9375rem;line-height:1.6}.repository-installer__signed svg{width:1rem;flex:none;color:var(--mint-700)}
.repository-installer__prerequisite{display:flex;align-items:start;gap:.85rem;padding:1.35rem;border:1px solid #eddcbe;border-radius:.85rem;background:#fffaf2}.repository-installer__prerequisite>svg{flex:none;width:1.2rem;margin-top:.1rem;color:#9a601a}.repository-installer__prerequisite>div{min-width:0}.repository-installer__prerequisite strong{font-size:.95rem;font-weight:600}
.repository-installer p{margin:.5rem 0 0;color:var(--ink-600);font-size:1rem;line-height:1.75}.repository-installer details{min-width:0}.repository-installer summary{min-height:2.75rem;align-content:center;cursor:pointer;font-size:.9375rem;font-weight:550;line-height:1.6}
.repository-installer__prerequisite details{margin-top:.8rem}.repository-installer__prerequisite .command-snippet{margin-top:.8rem}.repository-installer__step h3{margin:0 0 .8rem;font-size:1.05rem;font-weight:600;letter-spacing:-.025em}
.repository-installer__label{display:flex;justify-content:space-between;align-items:baseline;gap:.8rem;flex-wrap:wrap;margin-bottom:.8rem}.repository-installer__label h3{margin:0}.repository-installer__label>span{font-size:.9375rem;color:var(--ink-500)}
p.repository-installer__note{display:flex;gap:.6rem;align-items:start;margin:0;font-size:1rem}.repository-installer__note svg{width:1rem;margin-top:.2rem;flex:none}
.repository-installer__details{padding-top:.85rem;border-top:1px solid var(--border)}.repository-installer__details .command-snippet{margin-top:.8rem}
@media(max-width:520px){.repo-options{width:100%}.repo-options button{flex:1;min-width:0;padding:.75rem}.repository-installer__signed{max-width:none}.repository-installer__prerequisite{padding:1rem}}
</style>
