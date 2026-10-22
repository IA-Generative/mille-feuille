<script setup lang="ts">
export interface ToolSourceOption {
  id: string;
  label: string;
  count: number;
}

defineProps<{ options: ToolSourceOption[] }>();
const source = defineModel<string>({ required: true });
</script>

<template>
  <div class="tool-source-filter" role="group" aria-label="Filtrer par source">
    <button
      v-for="option in options"
      :key="option.id"
      type="button"
      class="tool-source-filter__chip"
      :class="{ 'tool-source-filter__chip--active': source === option.id }"
      :aria-pressed="source === option.id"
      @click="source = option.id"
    >
      {{ option.label }} <span class="tool-source-filter__count">{{ option.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.tool-source-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.tool-source-filter__chip {
  padding: 0.3rem 0.85rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 999px;
  background: var(--background-default-grey);
  font: inherit;
  font-size: 0.8125rem;
  cursor: pointer;
}

.tool-source-filter__chip--active {
  background: #6a5cff1a;
  border-color: #6a5cff;
  color: #4b3fd9;
  font-weight: 600;
}

.tool-source-filter__count {
  margin-left: 0.25rem;
  color: var(--text-mention-grey);
}
</style>
