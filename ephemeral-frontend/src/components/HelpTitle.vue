<script setup lang="ts">
import { ref, useId } from "vue";

/** Un titre de section avec un « i » qui déplie une aide (à quoi ça sert, comment remplir) ; fermée par défaut. */
defineProps<{ title: string; helpLabel: string }>();

const open = ref(false);
const panelId = useId();
</script>

<template>
  <div class="help-title fr-mt-4w">
    <div class="line">
      <h2 class="fr-h5 title">{{ title }}</h2>
      <button
        type="button"
        class="info"
        :aria-expanded="open"
        :aria-controls="panelId"
        :title="helpLabel"
        @click="open = !open"
        @keydown.esc="open = false"
      >
        <span aria-hidden="true">i</span>
        <span class="fr-sr-only">{{ helpLabel }}</span>
      </button>
    </div>
    <div v-if="open" :id="panelId" class="panel fr-text--sm" role="note">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.line {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.title {
  margin: 0;
}
.info {
  flex: 0 0 auto;
  width: 1.5rem;
  height: 1.5rem;
  padding: 0;
  border: 1.5px solid var(--border-action-high-blue-france);
  border-radius: 50%;
  background: none;
  color: var(--text-action-high-blue-france);
  font: italic 700 0.95rem/1 Georgia, "Times New Roman", serif;
  cursor: pointer;
}
.info[aria-expanded="true"] {
  background: var(--background-action-high-blue-france);
  color: #fff;
}
.panel {
  margin-top: 0.75rem;
  padding: 0.9rem 1.1rem;
  border-left: 3px solid var(--border-action-high-blue-france);
  border-radius: 0.25rem;
  background: var(--background-alt-blue-france);
}
.panel :deep(p) {
  margin: 0 0 0.5rem;
}
.panel :deep(ul) {
  margin: 0;
  padding-left: 1.1rem;
}
.panel :deep(li) {
  margin-bottom: 0.35rem;
}
</style>
