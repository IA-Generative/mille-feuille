<script setup lang="ts">
import { useKnowledgeCollections } from "@/composables/useKnowledgeCollections";
import ToolTestButton from "@/components/tools/ToolTestButton.vue";
import type { Tool } from "@/types/tool";
import { TOOLS_PREVIEW } from "@/utils/featureFlags";

defineProps<{ tool: Tool }>();
const { selected: collections } = useKnowledgeCollections();
const selected = defineModel<string[]>({ required: true });
</script>

<template>
  <li class="tool-picker-row">
    <DsfrCheckbox :id="`pick-${tool.id}`" v-model="selected" :name="`pick-${tool.id}`" :value="tool.id" small>
      <template #label>
        <span class="tool-picker-row__name">{{ tool.name }}</span>
        <span class="tool-picker-row__description">{{ tool.description }}</span>
        <span v-if="TOOLS_PREVIEW && tool.config === 'collections'" class="tool-picker-row__config">
          <VIcon name="ri-book-2-line" scale="0.7" /> {{ collections.length }} collection{{ collections.length > 1 ? "s" : "" }} de l'analyse
        </span>
      </template>
    </DsfrCheckbox>
    <span class="tool-picker-row__actions">
      <DsfrBadge v-if="tool.sideEffect" class="tool-badge-nowrap" label="Confirmation dans le chat" type="warning" small no-icon />
      <ToolTestButton :tool="tool" />
    </span>
  </li>
</template>

<style scoped>
.tool-picker-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.4rem 0;
}

.tool-picker-row__actions {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.tool-picker-row__config {
  margin-left: 0.75rem;
  font-size: 0.75rem;
  color: #4b3fd9;
}

.tool-picker-row__name {
  font-weight: 600;
  margin-right: 0.75rem;
}

.tool-picker-row__description {
  color: var(--text-mention-grey);
  font-size: 0.8125rem;
}

.tool-badge-nowrap {
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
