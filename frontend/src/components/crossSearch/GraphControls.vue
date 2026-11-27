<script setup lang="ts">
/** Zoom et recadrage, utilisables au clavier (la molette et le glisser restent disponibles). */
const emit = defineEmits<{ zoomIn: []; zoomOut: []; reset: [] }>();
</script>

<template>
  <div class="graph-controls" role="group" aria-label="Affichage du graphe">
    <DsfrButton label="Zoomer" title="Zoomer" icon="ri-add-line" icon-only tertiary size="sm" @click="emit('zoomIn')" />
    <DsfrButton label="Dézoomer" title="Dézoomer" icon="ri-subtract-line" icon-only tertiary size="sm" @click="emit('zoomOut')" />
    <DsfrButton label="Recentrer" title="Recentrer" icon="ri-focus-3-line" icon-only tertiary size="sm" @click="emit('reset')" />
  </div>
</template>

<style scoped>
.graph-controls {
  position: absolute;
  right: 0.75rem;
  bottom: 0.75rem;
  display: flex;
  flex-direction: column;
  background: var(--background-default-grey);
}
</style>
