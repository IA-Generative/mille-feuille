<script setup lang="ts">
import type { KnowledgeCollection } from "@/types/knowledge";

defineProps<{ collection: KnowledgeCollection }>();
const selected = defineModel<string[]>({ required: true });
</script>

<template>
  <li class="collection-row">
    <DsfrCheckbox :id="`col-${collection.id}`" v-model="selected" :name="`col-${collection.id}`" :value="collection.id" small>
      <template #label>
        <span class="collection-row__name">{{ collection.name }}</span>
        <span class="collection-row__description">{{ collection.description }}</span>
      </template>
    </DsfrCheckbox>
    <span class="collection-row__count">{{ collection.documentCount.toLocaleString("fr-FR") }} documents</span>
  </li>
</template>

<style scoped>
.collection-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
}

.collection-row__name {
  font-weight: 600;
  margin-right: 0.75rem;
}

.collection-row__description {
  color: var(--text-mention-grey);
  font-size: 0.8125rem;
}

.collection-row__count {
  flex-shrink: 0;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
  white-space: nowrap;
}
</style>
