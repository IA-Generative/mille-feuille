<script setup lang="ts">
// Fichiers choisis avant l'envoi (création d'un dossier, ajout de documents), avec un bouton pour retirer chacun.
defineProps<{ files: File[] }>();
const emit = defineEmits<{ remove: [index: number] }>();

function formatSize(bytes: number) {
  return bytes < 1_000_000 ? `${Math.round(bytes / 1000)} Ko` : `${(bytes / 1_000_000).toFixed(1)} Mo`;
}
</script>

<template>
  <ul v-if="files.length > 0" class="fr-raw-list fr-mt-2w">
    <li v-for="(file, index) in files" :key="`${file.name}-${index}`" class="fr-grid-row fr-grid-row--middle fr-grid-row--gutters fr-mb-1w">
      <span class="fr-col fr-text--sm fr-mb-0">{{ file.name }} ({{ formatSize(file.size) }})</span>
      <DsfrButton 
      :label="`Retirer le fichier ${file.name}`"
      icon-only
      tertiary
      no-outline
      icon="ri-close-line"
      size="sm"
      @click="emit('remove', index)"
      />
    </li>
  </ul>
</template>
