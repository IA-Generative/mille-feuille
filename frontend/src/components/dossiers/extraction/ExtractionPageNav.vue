<script setup lang="ts">
defineProps<{ index: number; total: number; pageNumber: number }>();
const emit = defineEmits<{ goto: [index: number] }>();
</script>

<template>
  <nav class="extraction-nav" aria-label="Pagination des pages">
    <button type="button" class="fr-btn fr-btn--tertiary fr-btn--sm" :disabled="index === 0" @click="emit('goto', index - 1)">
      Page précédente
    </button>
    <span class="fr-text--sm extraction-nav__count" aria-live="polite">Page {{ pageNumber }} sur {{ total }}</span>
    <button
      type="button"
      class="fr-btn fr-btn--tertiary fr-btn--sm"
      :disabled="index >= total - 1"
      @click="emit('goto', index + 1)"
    >
      Page suivante
    </button>
  </nav>
</template>

<style scoped>
.extraction-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.extraction-nav__count {
  margin: 0;
  color: var(--text-mention-grey);
}
</style>
