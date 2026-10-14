<script setup lang="ts">
// Fichiers choisis avant l'envoi (création d'un dossier, ajout de documents), avec un bouton pour retirer chacun.
defineProps<{ files: File[] }>();
const emit = defineEmits<{ remove: [index: number] }>();

function formatSize(bytes: number) {
  return bytes < 1_000_000 ? `${Math.round(bytes / 1000)} Ko` : `${(bytes / 1_000_000).toFixed(1)} Mo`;
}
</script>

<template>
  <ul v-if="files.length > 0" class="document-file-list">
    <li v-for="(file, index) in files" :key="`${file.name}-${index}`" class="document-file-list__file">
      <span>{{ file.name }} ({{ formatSize(file.size) }})</span>
      <DsfrButton label="Retirer le fichier" icon-only tertiary icon="ri-close-line" size="sm" @click="emit('remove', index)" />
    </li>
  </ul>
</template>

<style scoped>
.document-file-list {
  list-style: none;
  margin: 1rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.document-file-list__file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.25rem;
}
</style>
