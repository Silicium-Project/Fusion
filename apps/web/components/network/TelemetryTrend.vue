<template>
  <section class="telemetry-trend" :aria-label="title">
    <header class="telemetry-trend__head">
      <h3>{{ title }}</h3>
      <span>{{ t('observability.telemetry.sinceShort') }}</span>
    </header>
    <div class="telemetry-trend__legend">
      <span v-for="line in lines" :key="line.key"
        ><i :style="{ background: line.color }"></i>{{ line.label
        }}<strong>{{ latest(line.key) }}</strong></span
      >
    </div>
    <template v-if="hasData">
      <div
        class="telemetry-trend__plot"
        role="img"
        :aria-label="`${title}. ${t('observability.telemetry.sampleCount', { count: measuredSamples.length })}. ${lines.map((line) => `${line.label} ${latest(line.key)}`).join('. ')}`"
      >
        <div class="telemetry-trend__y" aria-hidden="true">
          <span v-for="tick in ticks" :key="tick">{{ tick }}</span>
        </div>
        <div class="telemetry-trend__grid" aria-hidden="true">
          <svg viewBox="0 0 720 180" preserveAspectRatio="none">
            <g
              v-for="line in lines"
              :key="line.key"
              :stroke="line.color"
              fill="none"
              stroke-width="1.8"
            >
              <polyline
                v-for="(path, index) in paths(line.key)"
                :key="index"
                :points="path"
                vector-effect="non-scaling-stroke"
              />
              <circle
                v-for="(point, index) in points(line.key)"
                :key="`p-${index}`"
                :cx="point.x"
                :cy="point.y"
                r="2.4"
                :fill="line.color"
                stroke="none"
                vector-effect="non-scaling-stroke"
              />
            </g>
          </svg>
        </div>
        <div class="telemetry-trend__x" aria-hidden="true">
          <span>{{ axisTime(firstAt) }}</span
          ><span>{{ axisTime(lastAt) }}</span>
        </div>
      </div>
      <p v-if="measuredSamples.length === 1" class="telemetry-trend__note">
        {{ t('observability.telemetry.single') }}
      </p>
      <details class="telemetry-trend__data">
        <summary>{{ t('observability.telemetry.table') }}</summary>
        <div class="table-wrap">
          <table class="data-table">
            <caption class="sr-only">
              {{
                title
              }}
            </caption>
            <thead>
              <tr>
                <th scope="col">{{ t('observability.telemetry.time') }}</th>
                <th v-for="line in lines" :key="line.key" scope="col">{{ line.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="sample in measuredSamples.slice(-20).reverse()" :key="sample.at">
                <th scope="row">{{ time(sample.at) }}</th>
                <td v-for="line in lines" :key="line.key">{{ value(sample[line.key]) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </template>
    <div v-else class="telemetry-trend__empty">
      <UiIcon name="activity" /><strong>{{ t('observability.telemetry.empty') }}</strong>
      <p>{{ t('observability.telemetry.emptyText') }}</p>
    </div>
    <footer>
      {{ t('observability.telemetry.since')
      }}<span>{{
        t('observability.telemetry.sampleCount', { count: measuredSamples.length })
      }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import type { TelemetrySample } from '~/utils/telemetry';
import { intlLocale } from '~/utils/i18n';
type Key = 'cpu' | 'memory' | 'queue' | 'active';
const props = withDefaults(
  defineProps<{ title: string; samples: TelemetrySample[]; mode?: 'resources' | 'tasks' }>(),
  { mode: 'resources' },
);
const { t } = useI18n();
const lines = computed<{ key: Key; label: string; color: string }[]>(() =>
  props.mode === 'tasks'
    ? [
        { key: 'queue', label: t('observability.telemetry.queue'), color: '#216dcc' },
        { key: 'active', label: t('observability.telemetry.active'), color: '#14294a' },
      ]
    : [
        { key: 'cpu', label: `${t('observability.telemetry.cpu')} (%)`, color: '#216dcc' },
        { key: 'memory', label: `${t('observability.telemetry.memory')} (%)`, color: '#14294a' },
      ],
);
const measuredSamples = computed(() =>
  props.samples.filter((sample) => lines.value.some((line) => sample[line.key] !== null)),
);
const hasData = computed(() => measuredSamples.value.length > 0);
const firstAt = computed(() => props.samples[0]?.at || 0);
const lastAt = computed(() => props.samples.at(-1)?.at || firstAt.value);
const maximum = computed(() =>
  props.mode === 'resources'
    ? 100
    : Math.max(
        4,
        Math.ceil(
          Math.max(
            0,
            ...props.samples.flatMap((sample) => lines.value.map((line) => sample[line.key] || 0)),
          ) / 4,
        ) * 4,
      ),
);
const ticks = computed(() =>
  [maximum.value, maximum.value * 0.75, maximum.value * 0.5, maximum.value * 0.25, 0].map((tick) =>
    new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 0 }).format(tick),
  ),
);
const time = (at: number) =>
  at
    ? new Intl.DateTimeFormat(intlLocale(), {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }).format(at)
    : '—';
const axisTime = (at: number) =>
  at
    ? new Intl.DateTimeFormat(intlLocale(), { hour: '2-digit', minute: '2-digit' }).format(at)
    : '—';
const value = (number: number | null) =>
  number === null
    ? '—'
    : new Intl.NumberFormat(intlLocale(), {
        maximumFractionDigits: props.mode === 'resources' ? 1 : 0,
      }).format(number);
const latest = (key: Key) => value(props.samples.at(-1)?.[key] ?? null);
const x = (at: number) =>
  lastAt.value === firstAt.value
    ? 0
    : ((at - firstAt.value) / (lastAt.value - firstAt.value)) * 720;
const y = (number: number) => 180 - (Math.min(maximum.value, number) / maximum.value) * 180;
function paths(key: Key): string[] {
  const result: string[] = [];
  let current: string[] = [];
  let previous = 0;
  for (const sample of props.samples) {
    if (sample[key] === null || (previous && sample.at - previous > 25_000)) {
      if (current.length) result.push(current.join(' '));
      current = [];
    }
    if (sample[key] !== null) current.push(`${x(sample.at)},${y(sample[key]!)}`);
    previous = sample.at;
  }
  if (current.length) result.push(current.join(' '));
  return result;
}
function points(key: Key) {
  return props.samples
    .filter((sample) => sample[key] !== null)
    .map((sample) => ({ x: x(sample.at), y: y(sample[key]!) }));
}
</script>

<style scoped>
.telemetry-trend {
  min-width: 0;
}
.telemetry-trend__head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.75rem;
}
.telemetry-trend h3 {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: -0.025em;
}
.telemetry-trend__head > span {
  font-size: 0.9375rem;
  color: var(--ink-600);
}
.telemetry-trend__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.8rem 1.7rem;
  margin: 1.25rem 0;
  color: var(--ink-700);
  font-size: 0.9375rem;
}
.telemetry-trend__legend > span {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.telemetry-trend__legend i {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
}
.telemetry-trend__legend strong {
  font-family: var(--font-mono);
  font-weight: 500;
  color: var(--ink-950);
}
.telemetry-trend__plot {
  position: relative;
  min-width: 0;
  padding-left: 3rem;
}
.telemetry-trend__y {
  position: absolute;
  inset: 0 auto auto 0;
  height: 180px;
  display: flex;
  width: 2.5rem;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
  color: var(--ink-600);
  font: 400 0.9375rem/1 var(--font-mono);
}
.telemetry-trend__grid {
  height: 180px;
  border: 1px solid var(--border-strong);
  background:
    repeating-linear-gradient(
      to top,
      transparent 0,
      transparent calc(25% - 1px),
      #dfe8f2 calc(25% - 1px),
      #dfe8f2 25%
    ),
    repeating-linear-gradient(
      to right,
      transparent 0,
      transparent calc(20% - 1px),
      #edf2f8 calc(20% - 1px),
      #edf2f8 20%
    );
}
.telemetry-trend__grid svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}
.telemetry-trend__x > span {
  white-space: nowrap;
}
.telemetry-trend__x {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.3rem 1rem;
  margin-top: 0.5rem;
  color: var(--ink-600);
  font: 400 0.9375rem/1.5 var(--font-mono);
}
.telemetry-trend__note,
.telemetry-trend__empty p {
  color: var(--ink-600);
  font-size: 1rem;
  line-height: 1.7;
}
.telemetry-trend__empty {
  display: grid;
  justify-items: start;
  align-content: center;
  min-height: 190px;
  padding: 1.5rem;
  border: 1px dashed var(--border-strong);
  border-radius: 0.7rem;
  background: rgba(255, 255, 255, 0.5);
}
.telemetry-trend__empty > svg {
  width: 1.4rem;
  margin-bottom: 0.8rem;
  color: var(--mint-700);
}
.telemetry-trend__empty strong {
  font-size: 1rem;
}
.telemetry-trend__empty p {
  max-width: 42rem;
  margin: 0.5rem 0 0;
}
.telemetry-trend__data {
  margin-top: 1rem;
  font-size: 0.9375rem;
}
.telemetry-trend__data summary {
  min-height: 2.75rem;
  display: flex;
  align-items: center;
  color: var(--mint-700);
  cursor: pointer;
}
.telemetry-trend__data th {
  font-size: 0.9375rem;
  font-weight: 500;
}
.telemetry-trend footer {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  margin-top: 1rem;
  color: var(--ink-600);
  font-size: 0.9375rem;
  line-height: 1.6;
}
@media (max-width: 540px) {
  .telemetry-trend__head {
    align-items: start;
    flex-direction: column;
  }
  .telemetry-trend__grid {
    height: 170px;
  }
  .telemetry-trend__legend {
    gap: 0.7rem 1rem;
  }
  .telemetry-trend__plot {
    padding-left: 2.7rem;
  }
  .telemetry-trend__x {
    left: auto;
  }
  .telemetry-trend__y {
    width: 2.2rem;
    height: 170px;
  }
  .telemetry-trend__empty {
    padding: 1rem;
  }
}
</style>
