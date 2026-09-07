import { computed, onBeforeUnmount, onMounted, ref, toValue, watch } from 'vue';
import type { MaybeRefOrGetter } from 'vue';
import { sampleTelemetry } from '~/services/telemetry';

type UpdatedAt = string | Date | null | undefined;

interface LiveTelemetryOptions {
  baseNodes?: MaybeRefOrGetter<number>;
  baseActiveNodes?: MaybeRefOrGetter<number>;
  interval?: number;
  seed?: number;
  sourceUpdatedAt?: MaybeRefOrGetter<UpdatedAt>;
}

function timestamp(value: UpdatedAt): number | null {
  if (!value) return null;
  const parsed = value instanceof Date ? value.getTime() : new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

export function useLiveTelemetry(options: LiveTelemetryOptions = {}) {
  const tick = ref(0);
  const now = ref<number | null>(null);
  const localUpdatedAt = ref<string | null>(null);
  const isLive = ref(false);
  const reducedMotion = ref(false);
  const telemetry = ref(sampleTelemetry(0, options.seed || 0));
  let timer: ReturnType<typeof setInterval> | undefined;
  let mediaQuery: MediaQueryList | undefined;
  let visibilityHandler: (() => void) | undefined;
  let motionHandler: (() => void) | undefined;

  const nodes = computed(() => Math.max(0, Math.round(Number(toValue(options.baseNodes ?? 0)) || 0)));
  const activeNodes = computed(() => {
    const configured = options.baseActiveNodes ? Number(toValue(options.baseActiveNodes)) : Math.round(nodes.value * 0.74);
    return Math.max(0, Math.round(configured || 0));
  });
  const sourceUpdatedAt = computed<UpdatedAt>(() => options.sourceUpdatedAt ? toValue(options.sourceUpdatedAt) : null);
  const updatedAt = computed(() => sourceUpdatedAt.value || localUpdatedAt.value);
  const ageSeconds = computed(() => {
    const reference = timestamp(updatedAt.value);
    if (!reference || !now.value) return 0;
    return Math.max(0, Math.floor((now.value - reference) / 1000));
  });
  const updatedLabel = computed(() => {
    if (!updatedAt.value) return 'en attente';
    if (ageSeconds.value < 3) return 'à l’instant';
    if (ageSeconds.value < 60) return `il y a ${ageSeconds.value} s`;
    return `il y a ${Math.floor(ageSeconds.value / 60)} min`;
  });

  function updateSample() {
    tick.value += 1;
    telemetry.value = sampleTelemetry(tick.value, options.seed || 0);
    now.value = Date.now();
    if (!sourceUpdatedAt.value) localUpdatedAt.value = new Date(now.value).toISOString();
  }

  function stopTimer() {
    if (!timer) return;
    clearInterval(timer);
    timer = undefined;
  }

  function startTimer() {
    if (timer || reducedMotion.value || typeof window === 'undefined' || document.visibilityState !== 'visible') return;
    timer = setInterval(updateSample, Math.max(2_500, options.interval || 4_000));
  }

  function handleVisibility() {
    if (document.visibilityState === 'visible') {
      now.value = Date.now();
      updateSample();
      startTimer();
    } else {
      stopTimer();
    }
  }

  function handleMotionPreference() {
    reducedMotion.value = Boolean(mediaQuery?.matches);
    if (reducedMotion.value) stopTimer();
    else startTimer();
  }

  function refreshSample() {
    updateSample();
  }

  watch(sourceUpdatedAt, (value) => {
    if (value && typeof window !== 'undefined') now.value = Date.now();
  });

  onMounted(() => {
    now.value = Date.now();
    if (!sourceUpdatedAt.value) localUpdatedAt.value = new Date(now.value).toISOString();
    isLive.value = true;
    mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    reducedMotion.value = mediaQuery.matches;
    visibilityHandler = handleVisibility;
    motionHandler = handleMotionPreference;
    document.addEventListener('visibilitychange', visibilityHandler);
    mediaQuery.addEventListener?.('change', motionHandler);
    startTimer();
  });

  onBeforeUnmount(() => {
    stopTimer();
    if (visibilityHandler) document.removeEventListener('visibilitychange', visibilityHandler);
    if (motionHandler) mediaQuery?.removeEventListener?.('change', motionHandler);
  });

  return { tick, telemetry, nodes, activeNodes, updatedAt, updatedLabel, ageSeconds, isLive, refreshSample };
}
