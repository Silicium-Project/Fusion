<template>
  <div class="contact-page marketing-page">
    <section class="contact-layout marketing-container">
      <div v-reveal="'left'" class="contact-intro">
        <span class="marketing-kicker">{{ t('contact.kicker') }}</span>
        <h1 class="marketing-title">{{ t('contact.title') }}<br><em>{{ t('contact.titleEm') }}</em></h1>
        <p class="marketing-lede">{{ t('contact.lede') }}</p>
        <div class="contact-brief marketing-glass"><span class="contact-brief__label">{{ t('contact.briefLabel') }}</span><div v-for="(item, index) in tl('contact.brief')" :key="item"><span>0{{ index + 1 }}</span><p>{{ item }}</p></div></div>
        <div class="contact-details"><div><UiIcon name="activity" /><span><strong>{{ t('contact.productIdeas') }}</strong><small>{{ t('contact.productIdeasText') }}</small></span></div><div><UiIcon name="network" /><span><strong>{{ t('contact.experimental') }}</strong><small>{{ t('contact.experimentalText') }}</small></span></div></div>
      </div>
      <form v-reveal="'right'" class="contact-form marketing-glass" @submit.prevent="send">
        <div class="contact-form__head"><div><span class="marketing-kicker">{{ t('contact.formKicker') }}</span><h2>{{ t('contact.formTitle') }}</h2></div><small>{{ t('contact.byEmail') }}</small></div>
        <div class="contact-form__body">
          <div class="contact-form__grid"><label class="field"><span>{{ t('contact.name') }}</span><input v-model.trim="form.name" required class="input" autocomplete="name" :maxlength="LIMITS.contactName" :placeholder="t('contact.namePlaceholder')"></label><label class="field"><span>{{ t('contact.email') }}</span><input v-model.trim="form.email" required class="input" type="email" autocomplete="email" :maxlength="LIMITS.email" :placeholder="t('auth.emailPlaceholder')"></label></div>
          <label class="field"><span>{{ t('contact.subject') }}</span><select v-model="form.subject" class="select"><option v-for="(subject, index) in tl('contact.subjects')" :key="index" :value="index">{{ subject }}</option></select></label>
          <label class="field"><span>{{ t('contact.idea') }}</span><textarea v-model.trim="form.message" required minlength="20" :maxlength="LIMITS.contactMessage" class="textarea" :placeholder="t('contact.ideaPlaceholder')"></textarea></label>
          <UiNotice v-if="formError" tone="danger">{{ formError }}</UiNotice>
          <UiNotice v-else-if="notice" :tone="contactEmail ? 'success' : 'warning'">{{ notice }}</UiNotice>
          <UiButton type="submit" size="large" icon="arrow">{{ t('contact.submit') }}</UiButton>
        </div>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { emailProblem, LIMITS } from '~/utils/validation';
definePageMeta({ layout: 'public' });
const { t, tl } = useI18n();
const config = useRuntimeConfig();
const contactEmail = computed(() => String(config.public.contactEmail || ''));
const notice = ref('');
const formError = ref('');
const form = reactive({ name: '', email: '', subject: 0, message: '' });
/** Names and emails go into the body of the prepared email only. */
const oneLine = (value: string) => value.replace(/[\r\n]+/g, ' ').trim();
function send() {
  formError.value = '';
  const problem = emailProblem(form.email) || ([...form.message].length < 20 ? 'validation.messageShort' : '');
  if (problem) { formError.value = t(problem); return; }
  if (!contactEmail.value) { notice.value = t('contact.noAddress'); return; }
  const subject = tl('contact.subjects')[form.subject] || '';
  const body = `${t('contact.mailGreeting')}\n\n${form.message.slice(0, LIMITS.contactMessage)}\n\n${oneLine(form.name).slice(0, LIMITS.contactName)}\n${oneLine(form.email)}`;
  window.location.href = `mailto:${contactEmail.value}?subject=${encodeURIComponent(t('contact.mailSubject', { subject }))}&body=${encodeURIComponent(body)}`;
  notice.value = t('contact.opened');
}
useSeoMeta({ title: () => t('contact.seoTitle'), description: () => t('contact.seoDescription') });
</script>

<style scoped>
.contact-layout{display:grid;grid-template-columns:minmax(0,.94fr) minmax(27rem,1.06fr);align-items:center;gap:clamp(2.5rem,6vw,6rem);min-height:min(760px,calc(100svh - 5rem));padding-block:clamp(3rem,6vw,5.5rem)}.contact-intro{min-width:0}.contact-intro .marketing-title{max-width:680px;font-size:clamp(3rem,4.9vw,5.4rem)}.contact-brief{display:grid;gap:.75rem;max-width:500px;margin-top:2.2rem;padding:1.15rem;border-radius:1.2rem;background:linear-gradient(145deg,rgba(255,255,255,.65),rgba(225,248,243,.34))}.contact-brief__label{color:var(--ink-500);font-family:var(--font-mono);font-size:.853rem;letter-spacing:.07em;text-transform:uppercase}.contact-brief>div{display:grid;grid-template-columns:1.6rem 1fr;gap:.55rem;padding-top:.65rem;border-top:1px solid var(--border)}.contact-brief>div span{color:var(--mint-700);font-family:var(--font-mono);font-size:.857rem}.contact-brief p{margin:0;color:var(--ink-700);font-size:.922rem;line-height:1.5}.contact-details{display:flex;flex-wrap:wrap;gap:1.5rem;margin-top:2rem}.contact-details>div{display:flex;align-items:center;gap:.6rem}.contact-details svg{width:1rem;color:var(--mint-700)}.contact-details strong,.contact-details small{display:block}.contact-details strong{color:var(--ink-900);font-size:.905rem}.contact-details small{margin-top:.18rem;color:var(--ink-500);font-size:.874rem}
.contact-form{overflow:hidden;border-radius:1.7rem;background:linear-gradient(145deg,rgba(255,255,255,.8),rgba(227,249,245,.4));}.contact-form__head{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;padding:1.45rem 1.5rem;border-bottom:1px solid var(--border)}.contact-form__head h2{margin:.55rem 0 0;color:var(--ink-900);font-size:1.45rem;letter-spacing:-.045em}.contact-form__head small{padding-bottom:.18rem;color:var(--ink-500);font-size:.881rem}.contact-form__body{display:grid;gap:1rem;padding:1.5rem}.contact-form__grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.contact-form :deep(.ui-button){justify-self:end}
@media(max-width:900px){.contact-layout{grid-template-columns:1fr;align-items:start;min-height:auto;gap:3rem;padding-block:3.5rem 5rem}.contact-intro{max-width:700px}.contact-form{max-width:700px;width:100%}}
@media(max-width:560px){.contact-layout{padding-block:3rem 4rem}.contact-form{border-radius:1.3rem}.contact-form__head{align-items:flex-start;flex-direction:column;padding:1.15rem}.contact-form__body{padding:1.15rem}.contact-form__grid{grid-template-columns:1fr}.contact-form :deep(.ui-button){width:100%}.contact-details{align-items:flex-start;flex-direction:column;gap:1rem}.contact-brief{margin-top:2rem}}
</style>
