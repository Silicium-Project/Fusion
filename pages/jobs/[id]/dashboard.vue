<script setup lang="ts">
const route = useRoute();
await navigateTo(`/jobs/${route.params.id}`, { redirectCode: 301, replace: true });
</script>

<template><span class="sr-only">Redirection vers le détail de la tâche</span></template>
