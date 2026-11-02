<script setup lang="ts">
// Un bloc replié par défaut : son titre et son nombre d'éléments, le détail à un clic. Un `<details>` natif : le clavier,
// le lecteur d'écran et l'état ouvert/fermé sont gérés par le navigateur.
defineProps<{ title: string; count?: number; icon: string }>();
</script>

<template>
  <details class="presentation-section">
    <summary class="presentation-section__summary">
      <VIcon :name="icon" class="presentation-section__icon" aria-hidden="true" />
      <span class="presentation-section__title">{{ title }}</span>
      <span v-if="count !== undefined" class="presentation-section__count">{{ count }}</span>
      <VIcon name="ri-arrow-down-s-line" class="presentation-section__chevron" aria-hidden="true" />
    </summary>
    <div class="presentation-section__body">
      <slot />
    </div>
  </details>
</template>

<style scoped>
.presentation-section {
  border-top: 1px solid var(--border-default-grey);
}

.presentation-section__summary {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 0;
  list-style: none;
  cursor: pointer;
}

.presentation-section__summary::-webkit-details-marker {
  display: none;
}

.presentation-section__summary:focus-visible {
  outline: 2px solid var(--border-active-blue-france);
  outline-offset: 2px;
  border-radius: 0.5rem;
}

.presentation-section__icon {
  color: var(--text-mention-grey);
}

.presentation-section__title {
  flex: 1;
  font-weight: 500;
}

.presentation-section__count {
  color: var(--text-mention-grey);
  font-size: 0.875rem;
}

.presentation-section__chevron {
  color: var(--text-mention-grey);
  transition: transform 0.15s ease;
}

.presentation-section[open] .presentation-section__chevron {
  transform: rotate(180deg);
}

.presentation-section__body {
  padding: 0 0 1rem 2rem;
}

@media (prefers-reduced-motion: reduce) {
  .presentation-section__chevron {
    transition: none;
  }
}
</style>
