<template>
  <section ref="story" class="process-story" aria-labelledby="process-story-title">
    <div class="process-story__sticky">
      <div class="process-story__atmosphere" aria-hidden="true"></div>

      <div class="process-story__layout marketing-container">
        <div class="process-story__copy">
          <div class="process-story__eyebrow-row">
            <span class="process-story__eyebrow">{{ t('processFlow.eyebrow') }}</span>
            <span class="process-story__counter"><b>{{ activeStep.number }}</b> / {{ total }}</span>
          </div>

          <div class="process-story__message-slot">
            <article :key="activeStep.id" class="process-story__message">
              <span class="process-story__step">{{ activeStep.kicker }}</span>
              <h3 id="process-story-title">{{ activeStep.title }}</h3>
              <p>{{ activeStep.text }}</p>
              <div class="process-story__outcome">
                <span class="process-story__outcome-icon"><UiIcon name="check" /></span>
                <span><small>{{ t('processFlow.atThisStep') }}</small><strong>{{ activeStep.result }}</strong></span>
              </div>
            </article>
          </div>

          <nav class="process-story__nav" :aria-label="t('processFlow.navAria')">
            <button
              v-for="(step, index) in steps"
              :key="step.id"
              type="button"
              :class="{ 'is-active': index === activeIndex }"
              :aria-current="index === activeIndex ? 'step' : undefined"
              @click="scrollToStep(index)"
            >
              <span>{{ step.number }}</span>
              <strong>{{ step.navLabel }}</strong>
              <i aria-hidden="true"></i>
            </button>
          </nav>
          <p class="process-story__hint"><span aria-hidden="true"></span>{{ t('processFlow.hint') }}</p>
        </div>

        <div class="process-story__network-wrap">
          <div class="process-story__network">
            <ClientOnly>
              <ProcessGraph3D :nodes="graphNodes" :active-node-id="activeNodeId" :active-phase="activeIndex" />
              <template #fallback>
                <div class="process-story__graph-fallback">{{ t('processFlow.loading3d') }}</div>
              </template>
            </ClientOnly>
          </div>
          <div class="process-story__network-caption"><span></span>{{ activeStep.networkCaption }}</div>
        </div>
      </div>

      <div class="process-story__progress" aria-hidden="true"><span :style="{ width: `${storyProgress * 100}%` }"></span></div>
    </div>
  </section>
</template>

<script setup lang="ts">
type Tone = 'mint' | 'violet' | 'blue' | 'amber';
type ProcessStep = {
  id: string;
  number: string;
  navLabel: string;
  kicker: string;
  title: string;
  text: string;
  result: string;
  networkCaption: string;
};

const { t, tl } = useI18n();
const stepIds = ['send', 'share', 'compute', 'return'];
const steps = computed<ProcessStep[]>(() => tl<Omit<ProcessStep, 'id' | 'number'>>('processFlow.steps').map((step, index) => ({ ...step, id: stepIds[index] || `step-${index}`, number: `0${index + 1}` })));

const graphNodes = computed(() => [
  { id: 'source', label: t('processFlow.nodes.source'), phase: 0, x: -3.8, y: 2.1, z: 0.3, tone: 'mint' as Tone },
  { id: 'relay-a', label: t('processFlow.nodes.relayA'), phase: 1, x: 2.7, y: 1.6, z: -1.9, tone: 'violet' as Tone },
  { id: 'relay-b', label: t('processFlow.nodes.relayB'), phase: 1, x: -2.8, y: -1.9, z: 1.6, tone: 'mint' as Tone },
  { id: 'compute-a', label: t('processFlow.nodes.computeA'), phase: 2, x: 3.6, y: -1.3, z: 1.8, tone: 'blue' as Tone },
  { id: 'compute-b', label: t('processFlow.nodes.computeB'), phase: 2, x: -0.3, y: 3, z: -3, tone: 'violet' as Tone },
  { id: 'result', label: t('processFlow.nodes.result'), phase: 3, x: 0.4, y: -3.1, z: 2.8, tone: 'amber' as Tone },
]);

const stepNodeIds = ['source', 'relay-a', 'compute-a', 'result'];
const story = ref<HTMLElement | null>(null);
const storyProgress = ref(0);
const requestedIndex = ref<number | null>(null);
const scrollIndex = computed(() => Math.min(steps.value.length - 1, Math.floor(Math.min(storyProgress.value + 0.001, 0.999999) * steps.value.length)));
const activeIndex = computed(() => requestedIndex.value ?? scrollIndex.value);
const activeStep = computed(() => steps.value[activeIndex.value] || steps.value[0]!);
const activeNodeId = computed(() => stepNodeIds[activeIndex.value] || stepNodeIds[0]);
const total = computed(() => String(steps.value.length).padStart(2, '0'));

function updateProgress() {
  const section = story.value || document.querySelector<HTMLElement>('.process-story');
  if (!section) return;
  const scrollable = Math.max(1, section.offsetHeight - window.innerHeight);
  storyProgress.value = Math.max(0, Math.min(1, -section.getBoundingClientRect().top / scrollable));

  if (requestedIndex.value !== null) {
    const requestedProgress = (requestedIndex.value + 0.5) / steps.value.length;
    if (Math.abs(storyProgress.value - requestedProgress) < 0.08) requestedIndex.value = null;
  }
}

function scrollToStep(index: number) {
  const section = story.value || document.querySelector<HTMLElement>('.process-story');
  if (!section) return;

  // The selected node changes immediately. The scroll only brings the story
  // into sync; the WebGL component derives a fresh camera destination from
  // that node's XYZ coordinates instead of following a predefined path.
  requestedIndex.value = index;
  const scrollable = Math.max(1, section.offsetHeight - window.innerHeight);
  const top = window.scrollY + section.getBoundingClientRect().top + scrollable * ((index + 0.5) / steps.value.length);
  window.scrollTo({ top, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
}

onMounted(() => {
  updateProgress();
  window.addEventListener('scroll', updateProgress, { passive: true });
  window.addEventListener('resize', updateProgress);
});

onBeforeUnmount(() => {
  window.removeEventListener('scroll', updateProgress);
  window.removeEventListener('resize', updateProgress);
});
</script>

<style scoped>
.process-story{position:relative;width:100vw;min-height:300svh;margin-left:calc(50% - 50vw);overflow:clip;background:linear-gradient(180deg,#eef7f5 0%,#f8faf8 38%,#f3f5fb 72%,#f8f8f5 100%)}.process-story__sticky{position:sticky;top:0;display:flex;height:100svh;min-height:38rem;align-items:center;overflow:hidden}.process-story__atmosphere{position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at 78% 43%,rgba(19,191,174,.15),transparent 33rem),radial-gradient(circle at 15% 76%,rgba(118,105,232,.11),transparent 30rem),linear-gradient(90deg,rgba(255,255,255,.28) 1px,transparent 1px) 0 0/5rem 5rem,linear-gradient(rgba(255,255,255,.25) 1px,transparent 1px) 0 0/5rem 5rem;mask-image:linear-gradient(180deg,transparent,#000 17%,#000 84%,transparent)}.process-story__layout{position:relative;z-index:1;display:grid;grid-template-columns:minmax(18rem,.7fr) minmax(0,1.3fr);align-items:center;gap:clamp(3rem,6vw,6rem);height:100%;padding-block:clamp(5rem,8vw,7rem) 2rem}.process-story__copy{min-width:0}.process-story__eyebrow-row{display:flex;align-items:center;justify-content:space-between;gap:1rem}.process-story__eyebrow,.process-story__step{color:var(--mint-700);font-family:var(--font-mono);font-size:.9375rem;font-weight:650;letter-spacing:.1em;text-transform:uppercase}.process-story__counter{color:var(--ink-500);font-family:var(--font-mono);font-size:.9375rem}.process-story__counter b{color:var(--ink-900);font-size:.966rem}.process-story__message{min-height:22rem;padding-top:1.15rem}.process-story__step{display:block;color:var(--ink-500)}.process-story__message h3{max-width:31rem;margin:1rem 0 0;color:var(--ink-900);font-size:clamp(2.65rem,4.8vw,5rem);font-weight:650;line-height:.96;letter-spacing:-.075em}.process-story__message p{max-width:28rem;margin:1.45rem 0 0;color:var(--ink-700);font-size:1.04rem;line-height:1.75}.process-story__outcome{display:flex;align-items:center;gap:.75rem;max-width:24rem;margin-top:1.6rem;padding:.72rem;border:1px solid rgba(255,255,255,.86);border-radius:.95rem;background:rgba(255,255,255,.54);box-shadow:inset 0 1px 0 rgba(255,255,255,.94),inset 0 0 0 1px rgba(21,40,61,.06),0 14px 30px rgba(19,32,51,.07);backdrop-filter:blur(18px)}.process-story__outcome-icon{display:grid;width:2.15rem;height:2.15rem;flex:none;place-items:center;border-radius:.7rem;background:var(--mint-100);color:var(--mint-700)}.process-story__outcome-icon svg{width:.9rem}.process-story__outcome small,.process-story__outcome strong{display:block}.process-story__outcome small{color:var(--ink-500);font-size:.9375rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase}.process-story__outcome strong{margin-top:.23rem;color:var(--ink-900);font-size:.9375rem}.process-story__nav{display:grid;gap:.18rem;max-width:24rem}.process-story__nav button{position:relative;display:grid;grid-template-columns:2rem 1fr;align-items:center;gap:.55rem;padding:.62rem .7rem;border:0;border-radius:.7rem;background:transparent;color:var(--ink-500);text-align:left;cursor:pointer;transition:background .3s ease,color .3s ease,transform .3s var(--ease-spring)}.process-story__nav button:hover{background:rgba(255,255,255,.48);color:var(--ink-800);transform:translateX(4px)}.process-story__nav button.is-active{background:rgba(255,255,255,.67);color:var(--ink-900);box-shadow:inset 0 1px 0 rgba(255,255,255,.9),0 7px 18px rgba(19,32,51,.05)}.process-story__nav button>span{color:var(--mint-700);font-family:var(--font-mono);font-size:.9375rem}.process-story__nav button strong{font-size:.9375rem;font-weight:720}.process-story__nav button i{position:absolute;top:.55rem;bottom:.55rem;left:0;width:2px;border-radius:99px;background:var(--mint-500);opacity:0;transform:scaleY(.35);transition:opacity .3s ease,transform .3s var(--ease-out)}.process-story__nav button.is-active i{opacity:1;transform:scaleY(1)}.process-story__hint{display:flex;align-items:center;gap:.5rem;margin:1.5rem 0 0;color:var(--ink-500);font-family:var(--font-mono);font-size:.9375rem;letter-spacing:.03em}.process-story__hint span{width:.42rem;height:.65rem;border:1px solid var(--mint-500);border-radius:99px;animation:story-scroll-hint 1.7s ease-in-out infinite}.process-story__network-wrap{position:relative;display:grid;place-items:center;min-width:0;height:min(74vh,730px)}.process-story__network{position:relative;width:min(100%,820px);height:100%;min-height:31rem}.process-story__network-caption{position:absolute;right:2%;bottom:-.9rem;display:flex;align-items:center;gap:.45rem;color:var(--ink-500);font-family:var(--font-mono);font-size:.9375rem}.process-story__network-caption span{width:.38rem;height:.38rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 .25rem rgba(19,191,174,.1)}.process-story__graph-fallback{display:grid;height:100%;place-items:center;border:1px solid rgba(255,255,255,.8);border-radius:2rem;background:rgba(255,255,255,.48);color:var(--ink-500);font-family:var(--font-mono);font-size:.9375rem}.process-story__progress{position:absolute;right:0;bottom:0;left:0;height:4px;background:rgba(21,40,61,.08)}.process-story__progress span{display:block;height:100%;background:linear-gradient(90deg,var(--mint-500),var(--violet-500),#df9a3e);transition:width .08s linear}.story-copy-enter-active,.story-copy-leave-active{transition:opacity .42s var(--ease-out),transform .42s var(--ease-out),filter .42s var(--ease-out)}.story-copy-enter-from,.story-copy-leave-to{opacity:0;transform:translateY(20px);filter:blur(7px)}@keyframes story-scroll-hint{0%,100%{transform:translateY(0);opacity:.6}50%{transform:translateY(5px);opacity:1}}@media(max-width:1050px){.process-story__layout{grid-template-columns:minmax(15rem,.78fr) minmax(0,1.22fr);gap:2rem}.process-story__message h3{font-size:clamp(2.35rem,4.5vw,4rem)}.process-story__network-wrap{height:min(68vh,620px)}.process-story__network{min-height:26rem}}@media(max-width:760px){.process-story{min-height:310svh}.process-story__layout{grid-template-columns:1fr;align-content:center;gap:.8rem;padding-block:4.8rem 1.7rem}.process-story__copy{position:relative;z-index:2}.process-story__message{min-height:0;padding-top:.8rem}.process-story__message h3{max-width:31rem;font-size:clamp(2.35rem,10vw,3.8rem)}.process-story__message p{max-width:33rem;margin-top:.9rem;font-size:.983rem}.process-story__outcome{margin-top:1rem}.process-story__nav{grid-template-columns:repeat(4,minmax(0,1fr));max-width:none;margin-top:1.25rem;gap:.25rem}.process-story__nav button{grid-template-columns:1fr;gap:.2rem;padding:.55rem .45rem}.process-story__nav button strong{font-size:.9375rem}.process-story__nav button i{top:auto;right:.45rem;bottom:0;left:.45rem;width:auto;height:2px;transform:scaleX(.25);transform-origin:left}.process-story__nav button.is-active i{transform:scaleX(1)}.process-story__hint{margin-top:.85rem}.process-story__network-wrap{height:clamp(19rem,45vh,30rem);order:-1}.process-story__network{width:100%;height:100%;min-height:0}.process-story__network-caption{right:4%;bottom:-.75rem}}@media(max-width:520px){.process-story{min-height:325svh}.process-story__sticky{min-height:0}.process-story__layout{width:calc(100% - 1.5rem);padding-block:4.6rem 1.15rem}.process-story__message h3{font-size:clamp(2.18rem,10.4vw,3.2rem);letter-spacing:-.07em}.process-story__message p{font-size:.973rem;line-height:1.62}.process-story__outcome{max-width:none;padding:.62rem}.process-story__outcome strong{font-size:.9375rem}.process-story__nav button{padding-inline:.3rem}.process-story__nav button>span{font-size:.9375rem}.process-story__nav button strong{font-size:.9375rem}.process-story__network-wrap{height:clamp(18rem,40vh,23rem)}.process-story__network-caption{font-size:.9375rem}}@media(max-width:380px){.process-story__layout{width:calc(100% - 1.25rem);padding-top:4.4rem}.process-story__message h3{font-size:clamp(2rem,10.2vw,2.8rem)}.process-story__message p{font-size:.956rem}.process-story__network-wrap{height:17rem}.process-story__network-caption{display:none}}@media(prefers-reduced-motion:reduce){.process-story__hint span{animation:none}.process-story__progress span{transition:none}.story-copy-enter-active,.story-copy-leave-active{transition-duration:.01ms}}
.process-story__message-slot{min-height:22rem;contain:layout}.process-story__message{min-height:0}.process-story__network-wrap{contain:layout}.process-story__network{contain:layout paint}@media(max-width:760px){.process-story__message-slot{min-height:20rem}}@media(max-width:520px){.process-story__message-slot{min-height:20rem}}
</style>
