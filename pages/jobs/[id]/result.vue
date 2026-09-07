<script setup lang="ts">
const route = useRoute();
await navigateTo(`/jobs/${route.params.id}#result`, { redirectCode: 302, replace: true });
</script>

<template><span class="sr-only">Redirection vers le résultat de la tâche</span></template>
