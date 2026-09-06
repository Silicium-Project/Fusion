<template>
  <section class="contact-page content-width">
    <div class="contact-page__intro"><span class="eyebrow">Contact</span><h1>Une question ?<br><em>Parlons du calcul.</em></h1><p>Architecture, expérimentation ou participation au réseau : décrivez le contexte et l’équipe pourra reprendre la discussion au bon niveau.</p><div class="contact-page__details"><div><UiIcon name="network"/><span><strong>Projet distribué</strong><small>Contributions et intégrations</small></span></div><div><UiIcon name="shield"/><span><strong>Devnet</strong><small>Environnement expérimental</small></span></div></div></div>
    <form class="contact-form surface" @submit.prevent="send"><div class="contact-form__head"><span>Message</span><small>Réponse par e-mail</small></div><div class="contact-form__body"><div class="contact-form__grid"><label class="field"><span>Votre nom</span><input v-model.trim="form.name" required class="input" autocomplete="name" placeholder="Nom et prénom"></label><label class="field"><span>Votre e-mail</span><input v-model.trim="form.email" required class="input" type="email" autocomplete="email" placeholder="vous@exemple.fr"></label></div><label class="field"><span>Sujet</span><select v-model="form.subject" class="select"><option>Découvrir Silicium</option><option>Participer au réseau</option><option>Intégration technique</option><option>Autre demande</option></select></label><label class="field"><span>Votre message</span><textarea v-model.trim="form.message" required minlength="20" class="textarea" placeholder="Donnez-nous assez de contexte pour vous répondre utilement."></textarea></label><UiNotice v-if="notice" :tone="contactEmail ? 'success' : 'warning'">{{ notice }}</UiNotice><UiButton type="submit" size="large" icon="arrow">Préparer le message</UiButton></div></form>
  </section>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'public' });
const config = useRuntimeConfig();
const contactEmail = computed(() => String(config.public.contactEmail || ''));
const notice = ref('');
const form = reactive({ name: '', email: '', subject: 'Découvrir Silicium', message: '' });
function send() {
  if (!contactEmail.value) { notice.value = 'L’adresse de contact sera publiée prochainement. Votre message reste dans ce navigateur.'; return; }
  const body = `Bonjour,\n\n${form.message}\n\n${form.name}\n${form.email}`;
  window.location.href = `mailto:${contactEmail.value}?subject=${encodeURIComponent(`[Silicium] ${form.subject}`)}&body=${encodeURIComponent(body)}`;
  notice.value = 'Votre application e-mail a été ouverte avec le message préparé.';
}
useSeoMeta({ title: 'Contact — Silicium', description: 'Contactez l’équipe Silicium pour parler infrastructure, intégration ou participation au réseau.' });
</script>

<style scoped>
.contact-page{display:grid;min-height:calc(100vh - 4.75rem);grid-template-columns:.9fr 1.1fr;align-items:center;gap:clamp(3rem,9vw,9rem);padding-top:5rem;padding-bottom:5rem}.contact-page h1{margin:1rem 0 0;font-size:clamp(3.5rem,6vw,5.8rem);line-height:.92;letter-spacing:-.07em}.contact-page h1 em{color:var(--ink-400);font-style:normal;font-weight:600}.contact-page__intro>p{max-width:540px;margin:1.6rem 0 0;color:var(--ink-600);font-size:.85rem;line-height:1.8}.contact-page__details{display:flex;gap:2rem;margin-top:2.5rem}.contact-page__details>div{display:flex;align-items:center;gap:.65rem}.contact-page__details svg{width:1rem;color:var(--mint-700)}.contact-page__details strong,.contact-page__details small{display:block}.contact-page__details strong{font-size:.68rem}.contact-page__details small{margin-top:.18rem;color:var(--ink-500);font-size:.57rem}.contact-form{overflow:hidden}.contact-form__head{display:flex;align-items:center;justify-content:space-between;padding:1rem 1.25rem;border-bottom:1px solid var(--border)}.contact-form__head span{font-size:.78rem;font-weight:800}.contact-form__head small{color:var(--ink-500);font-size:.58rem}.contact-form__body{display:grid;gap:1rem;padding:1.25rem}.contact-form__grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.contact-form :deep(.ui-button){justify-self:end}
@media(max-width:800px){.contact-page{grid-template-columns:1fr;gap:3rem}.contact-page__intro{padding-top:2rem}}@media(max-width:520px){.contact-page{padding-top:3rem}.contact-page h1{font-size:clamp(3rem,15vw,4.2rem)}.contact-page__details{align-items:flex-start;flex-direction:column;gap:1rem}.contact-form__grid{grid-template-columns:1fr}.contact-form :deep(.ui-button){width:100%}}
</style>
