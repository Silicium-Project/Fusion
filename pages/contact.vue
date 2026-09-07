<template>
  <div class="contact-page marketing-page">
    <section class="contact-layout marketing-container">
      <div v-reveal="'left'" class="contact-intro">
        <span class="marketing-kicker">Boîte à idées</span>
        <h1 class="marketing-title">Une idée pour le réseau ?<br><em>Parlons-en.</em></h1>
        <p class="marketing-lede">Ce formulaire sert uniquement à proposer une idée, un usage ou une amélioration. Les tâches sont reçues et distribuées automatiquement par le service.</p>
        <div class="contact-brief marketing-glass"><span class="contact-brief__label">Ce que vous pouvez proposer</span><div><span>01</span><p>Un usage ou un type de projet à essayer</p></div><div><span>02</span><p>Une amélioration d’interface ou de suivi</p></div><div><span>03</span><p>Une idée de rôle, d’intégration ou de machine</p></div></div>
        <div class="contact-details"><div><UiIcon name="activity" /><span><strong>Idées produit</strong><small>Usages, parcours et priorités</small></span></div><div><UiIcon name="network" /><span><strong>Réseau expérimental</strong><small>Retours sur le devnet</small></span></div></div>
      </div>
      <form v-reveal="'right'" class="contact-form marketing-glass" @submit.prevent="send">
        <div class="contact-form__head"><div><span class="marketing-kicker">Proposer une idée</span><h2>Décrivez ce que vous imaginez.</h2></div><small>Envoi par e-mail</small></div>
        <div class="contact-form__body">
          <div class="contact-form__grid"><label class="field"><span>Votre nom</span><input v-model.trim="form.name" required class="input" autocomplete="name" placeholder="Nom et prénom"></label><label class="field"><span>Votre e-mail</span><input v-model.trim="form.email" required class="input" type="email" autocomplete="email" placeholder="vous@exemple.fr"></label></div>
          <label class="field"><span>Sujet</span><select v-model="form.subject" class="select"><option>Idée produit</option><option>Idée pour le réseau</option><option>Amélioration UX</option><option>Autre idée</option></select></label>
          <label class="field"><span>Votre idée</span><textarea v-model.trim="form.message" required minlength="20" class="textarea" placeholder="Décrivez l’idée, le problème qu’elle résout et ce que vous aimeriez voir."></textarea></label>
          <UiNotice v-if="notice" :tone="contactEmail ? 'success' : 'warning'">{{ notice }}</UiNotice>
          <UiButton type="submit" size="large" icon="arrow">Préparer l’idée</UiButton>
        </div>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'public' });
const config = useRuntimeConfig();
const contactEmail = computed(() => String(config.public.contactEmail || ''));
const notice = ref('');
const form = reactive({ name: '', email: '', subject: 'Idée produit', message: '' });
function send() {
  if (!contactEmail.value) { notice.value = 'L’adresse de contact sera publiée prochainement. Votre message reste dans ce navigateur.'; return; }
  const body = `Bonjour,\n\n${form.message}\n\n${form.name}\n${form.email}`;
  window.location.href = `mailto:${contactEmail.value}?subject=${encodeURIComponent(`[Silicium — idée] ${form.subject}`)}&body=${encodeURIComponent(body)}`;
  notice.value = 'Votre application e-mail a été ouverte avec l’idée préparée.';
}
useSeoMeta({ title: 'Idées — Silicium', description: 'Proposez une idée d’usage, d’interface ou de réseau à l’équipe Silicium.' });
</script>

<style scoped>
.contact-layout{display:grid;grid-template-columns:minmax(0,.94fr) minmax(27rem,1.06fr);align-items:center;gap:clamp(2.5rem,6vw,6rem);min-height:min(760px,calc(100svh - 5rem));padding-block:clamp(3rem,6vw,5.5rem)}.contact-intro{min-width:0}.contact-intro .marketing-title{max-width:680px;font-size:clamp(3rem,4.9vw,5.4rem)}.contact-brief{display:grid;gap:.75rem;max-width:500px;margin-top:2.2rem;padding:1.15rem;border-radius:1.2rem;background:linear-gradient(145deg,rgba(255,255,255,.65),rgba(225,248,243,.34))}.contact-brief__label{color:var(--ink-500);font-family:var(--font-mono);font-size:.57rem;letter-spacing:.07em;text-transform:uppercase}.contact-brief>div{display:grid;grid-template-columns:1.6rem 1fr;gap:.55rem;padding-top:.65rem;border-top:1px solid var(--border)}.contact-brief>div span{color:var(--mint-700);font-family:var(--font-mono);font-size:.58rem}.contact-brief p{margin:0;color:var(--ink-700);font-size:.77rem;line-height:1.5}.contact-details{display:flex;flex-wrap:wrap;gap:1.5rem;margin-top:2rem}.contact-details>div{display:flex;align-items:center;gap:.6rem}.contact-details svg{width:1rem;color:var(--mint-700)}.contact-details strong,.contact-details small{display:block}.contact-details strong{color:var(--ink-900);font-size:.72rem}.contact-details small{margin-top:.18rem;color:var(--ink-500);font-size:.63rem}
.contact-form{overflow:hidden;border-radius:1.7rem;background:linear-gradient(145deg,rgba(255,255,255,.8),rgba(227,249,245,.4));}.contact-form__head{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;padding:1.45rem 1.5rem;border-bottom:1px solid var(--border)}.contact-form__head h2{margin:.55rem 0 0;color:var(--ink-900);font-size:1.45rem;letter-spacing:-.045em}.contact-form__head small{padding-bottom:.18rem;color:var(--ink-500);font-size:.65rem}.contact-form__body{display:grid;gap:1rem;padding:1.5rem}.contact-form__grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.contact-form :deep(.ui-button){justify-self:end}
@media(max-width:900px){.contact-layout{grid-template-columns:1fr;align-items:start;min-height:auto;gap:3rem;padding-block:3.5rem 5rem}.contact-intro{max-width:700px}.contact-form{max-width:700px;width:100%}}
@media(max-width:560px){.contact-layout{padding-block:3rem 4rem}.contact-form{border-radius:1.3rem}.contact-form__head{align-items:flex-start;flex-direction:column;padding:1.15rem}.contact-form__body{padding:1.15rem}.contact-form__grid{grid-template-columns:1fr}.contact-form :deep(.ui-button){width:100%}.contact-details{align-items:flex-start;flex-direction:column;gap:1rem}.contact-brief{margin-top:2rem}}
</style>
