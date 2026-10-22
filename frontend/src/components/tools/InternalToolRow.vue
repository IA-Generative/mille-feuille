<script setup lang="ts">
import ToolTestButton from "@/components/tools/ToolTestButton.vue";
import type { Tool } from "@/types/tool";

defineProps<{ tool: Tool }>();
</script>

<template>
  <li class="internal-tool">
    <span class="internal-tool__icon"><VIcon name="ri-tools-line" /></span>
    <div class="internal-tool__text">
      <span class="internal-tool__name">{{ tool.name }}</span>
      <span class="internal-tool__description">{{ tool.description }}</span>
    </div>
    <DsfrBadge class="tool-badge-nowrap" v-if="tool.sideEffect" label="Modifie des données" type="warning" small no-icon />
    <ToolTestButton :tool="tool" />
  </li>
</template>

<style scoped>
.internal-tool {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: var(--background-default-grey);
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
}

.internal-tool__icon {
  display: inline-flex;
  color: var(--text-mention-grey);
}

.internal-tool__text {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.internal-tool__name {
  font-weight: 600;
  font-size: 0.9375rem;
}

.internal-tool__description {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.tool-badge-nowrap {
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
