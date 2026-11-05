<script setup lang="ts">
import { TYPE_ICONS, TYPE_LABELS, type LlmType } from "@/types/llmModel";

// Les types d'un modèle : lus sur le hub, jamais saisis. `null` : le hub n'a pas encore été lu pour ce modèle.
defineProps<{ types: LlmType[] | null }>();
</script>

<template>
  <ul v-if="types" class="type-chips" aria-label="Types du modèle, lus sur le hub">
    <li v-for="type in types" :key="type" class="type-chips__chip">
      <VIcon :name="TYPE_ICONS[type]" scale="0.8" aria-hidden="true" />
      {{ TYPE_LABELS[type] }}
    </li>
    <li v-if="!types.length" class="type-chips__none">Type non détecté</li>
  </ul>
  <p v-else class="type-chips__none">Pas encore lu sur le hub</p>
</template>

<style scoped>
.type-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.type-chips__chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.625rem;
  border-radius: 999px;
  border: 1px solid var(--border-default-grey, #ddd);
  color: var(--text-mention-grey, #666);
  font-size: 0.8125rem;
}

.type-chips__none {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--text-mention-grey, #666);
}
</style>
