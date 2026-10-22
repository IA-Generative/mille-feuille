<script setup lang="ts">
import { computed } from "vue";

import { useTools } from "@/composables/useTools";

const props = defineProps<{ toolIds: string[] }>();

const { allTools } = useTools();

const names = computed(() => {
  const byId = new Map(allTools().map((tool) => [tool.id, tool.name]));
  return props.toolIds.map((id) => byId.get(id) ?? id);
});
</script>

<template>
  <p v-if="names.length === 0" class="tool-selection-summary tool-selection-summary--empty">Aucun outil sélectionné.</p>
  <ul v-else class="tool-selection-summary">
    <li v-for="name in names" :key="name" class="tool-selection-summary__chip">{{ name }}</li>
  </ul>
</template>

<style scoped>
.tool-selection-summary {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.tool-selection-summary--empty {
  color: var(--text-mention-grey);
  font-size: 0.875rem;
}

.tool-selection-summary__chip {
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  background: #6a5cff14;
  color: #4b3fd9;
  font-size: 0.8125rem;
  font-weight: 500;
}
</style>
