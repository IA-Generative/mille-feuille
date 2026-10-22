<script setup lang="ts">
import { computed } from "vue";

import { useTools } from "@/composables/useTools";

const props = defineProps<{ toolIds: string[] }>();
// Un outil devenu indisponible n'est plus dans la modale de choix : la personne le retire ici.
const emit = defineEmits<{ remove: [toolId: string] }>();

const { allTools, isUnavailable } = useTools();

const chips = computed(() => {
  const byId = new Map(allTools().map((tool) => [tool.id, tool.name]));
  return props.toolIds.map((id) => ({
    id,
    name: byId.get(id) ?? "outil indisponible",
    unavailable: isUnavailable(id),
  }));
});
</script>

<template>
  <p v-if="chips.length === 0" class="tool-selection-summary tool-selection-summary--empty">Aucun outil sélectionné.</p>
  <ul v-else class="tool-selection-summary">
    <li
      v-for="chip in chips"
      :key="chip.id"
      class="tool-selection-summary__chip"
      :class="{ 'tool-selection-summary__chip--unavailable': chip.unavailable }"
      :title="chip.unavailable ? 'Cet outil n\'existe plus ou vous n\'y avez plus accès : retirez-le.' : undefined"
    >
      {{ chip.name }}
      <button
        v-if="chip.unavailable"
        type="button"
        class="tool-selection-summary__remove"
        :aria-label="`Retirer l'outil indisponible ${chip.id}`"
        @click="emit('remove', chip.id)"
      >
        <VIcon name="ri-close-line" scale="0.8" />
      </button>
    </li>
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
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  background: #6a5cff14;
  color: #4b3fd9;
  font-size: 0.8125rem;
  font-weight: 500;
}

.tool-selection-summary__chip--unavailable {
  background: #ce05001a;
  color: var(--text-default-error);
  text-decoration: line-through;
}

.tool-selection-summary__remove {
  display: inline-flex;
  padding: 0;
  border: none;
  background: none;
  color: inherit;
  cursor: pointer;
}
</style>
