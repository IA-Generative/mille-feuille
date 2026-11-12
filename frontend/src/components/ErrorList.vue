<script setup lang="ts">
// Liste de problèmes (validation d'un formulaire, fichiers refusés…) dans une alerte d'erreur DSFR.
// S'affiche seulement s'il y a au moins un message ; `alert` la fait annoncer par les lecteurs d'écran.
defineProps<{ errors: string[] }>();
</script>

<template>
  <DsfrAlert v-if="errors.length" alert type="error" small>
    <ul class="fr-my-0 fr-pl-2w">
      <li v-for="error in errors" :key="error">{{ error }}</li>
    </ul>
  </DsfrAlert>
</template>
