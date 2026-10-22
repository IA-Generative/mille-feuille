<script setup lang="ts">
import { computed } from "vue";

import ToolAuthBadge from "@/components/tools/ToolAuthBadge.vue";
import ToolPickerRow from "@/components/tools/ToolPickerRow.vue";
import type { Tool, ToolAuthMode } from "@/types/tool";

// `tools` : les lignes affichées sur la page courante ; `scope` : tous les tools du groupe que le filtre laisse passer
// (le compteur et « Tout sélectionner » portent sur eux, pas seulement sur la page).
const props = defineProps<{ title: string; tools: Tool[]; scope: Tool[]; authMode?: ToolAuthMode }>();
const selected = defineModel<string[]>({ required: true });

const selectedCount = computed(() => props.scope.filter((tool) => selected.value.includes(tool.id)).length);
const allSelected = computed(() => selectedCount.value === props.scope.length);

// Ne touche qu'aux tools du filtre courant, sur toutes les pages.
function toggleAll() {
  const ids = props.scope.map((tool) => tool.id);
  selected.value = allSelected.value
    ? selected.value.filter((id) => !ids.includes(id))
    : [...new Set([...selected.value, ...ids])];
}
</script>

<template>
  <section class="tool-picker-group">
    <header class="tool-picker-group__header">
      <h4 class="tool-picker-group__title">{{ title }}</h4>
      <ToolAuthBadge v-if="authMode" :mode="authMode" />
      <span class="tool-picker-group__count">{{ selectedCount }}/{{ scope.length }}</span>
      <DsfrButton
        :label="allSelected ? 'Tout retirer' : 'Tout sélectionner'"
        tertiary
        no-outline
        size="sm"
        class="tool-picker-group__toggle"
        @click="toggleAll"
      />
    </header>
    <ul class="tool-picker-group__list">
      <ToolPickerRow v-for="tool in tools" :key="tool.id" v-model="selected" :tool="tool" />
    </ul>
  </section>
</template>

<style scoped>
.tool-picker-group {
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
}

.tool-picker-group__header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.tool-picker-group__title {
  margin: 0;
  font-size: 0.9375rem;
}

.tool-picker-group__count {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.tool-picker-group__toggle {
  margin-left: auto;
}

.tool-picker-group__list {
  list-style: none;
  margin: 0.25rem 0 0;
  padding: 0;
}
</style>
