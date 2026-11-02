<script setup lang="ts">
// L'analyse n'est pas terminée : un état « en cours », sans résumé partiel. Annoncé aux lecteurs d'écran.
defineProps<{ dossierName: string }>();
</script>

<template>
  <div class="presentation-pending" role="status" aria-live="polite">
    <VIcon name="ri-loader-4-line" class="presentation-pending__spinner" aria-hidden="true" />
    <div>
      <p class="presentation-pending__title">Analyse en cours</p>
      <p class="presentation-pending__hint">
        La présentation de « {{ dossierName }} » apparaîtra ici dès que l'analyse sera terminée. Vous pouvez déjà
        poser vos questions.
      </p>
    </div>
  </div>
</template>

<style scoped>
.presentation-pending {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.presentation-pending p {
  margin: 0;
}

.presentation-pending__title {
  font-weight: 600;
}

.presentation-pending__hint {
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}

.presentation-pending__spinner {
  margin-top: 0.125rem;
  animation: presentation-spin 1.2s linear infinite;
  color: var(--text-mention-grey);
}

@keyframes presentation-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .presentation-pending__spinner {
    animation: none;
  }
}
</style>
