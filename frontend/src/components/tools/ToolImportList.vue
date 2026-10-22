<script setup lang="ts">
import type { Tool } from "@/types/tool";

defineProps<{ tools: Tool[] }>();
const selected = defineModel<string[]>({ required: true });
</script>

<template>
  <div class="tool-import-list">
    <p class="fr-text--sm tool-import-list__intro">
      {{ tools.length }} tools trouvés sur le serveur. Choisissez ceux que vous autorisez ; chaque agent pourra ensuite
      en retenir une partie.
    </p>
    <ul class="tool-import-list__items">
      <li v-for="tool in tools" :key="tool.id" class="tool-import-list__item">
        <DsfrCheckbox :id="`import-${tool.id}`" v-model="selected" :name="`import-${tool.id}`" :value="tool.id" small>
          <template #label>
            <span class="tool-import-list__name">{{ tool.name }}</span>
            <span class="tool-import-list__description">{{ tool.description }}</span>
          </template>
        </DsfrCheckbox>
        <DsfrBadge class="tool-badge-nowrap" v-if="tool.sideEffect" label="Modifie des données" type="warning" small no-icon />
      </li>
    </ul>
  </div>
</template>

<style scoped>
.tool-import-list__intro {
  margin: 0 0 1rem;
}

.tool-import-list__items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tool-import-list__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
}

.tool-import-list__name {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 600;
  margin-right: 0.75rem;
}

.tool-import-list__description {
  color: var(--text-mention-grey);
  font-size: 0.8125rem;
}

.tool-badge-nowrap {
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
