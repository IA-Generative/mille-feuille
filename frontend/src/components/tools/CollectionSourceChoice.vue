<script setup lang="ts">
import type { KnowledgeSource } from "@/types/knowledge";

defineProps<{ sources: KnowledgeSource[] }>();
const sourceId = defineModel<string>({ required: true });
</script>

<template>
  <div v-if="sources.length > 1" class="collection-source-choice" role="tablist" aria-label="Source de connaissances">
    <button
      v-for="source in sources"
      :key="source.id"
      type="button"
      role="tab"
      class="collection-source-choice__tab"
      :class="{ 'collection-source-choice__tab--selected': source.id === sourceId }"
      :aria-selected="source.id === sourceId"
      @click="sourceId = source.id"
    >
      {{ source.name }}
    </button>
  </div>
</template>

<style scoped>
.collection-source-choice {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.collection-source-choice__tab {
  padding: 0.25rem 0.75rem;
  border: 0;
  border-radius: 999px;
  background: var(--background-alt-grey);
  font-size: 0.8125rem;
  cursor: pointer;
}

.collection-source-choice__tab--selected {
  background: #4b3fd9;
  color: #fff;
}

.collection-source-choice__tab:focus-visible {
  outline: 2px solid #6a5cff;
  outline-offset: 2px;
}
</style>
