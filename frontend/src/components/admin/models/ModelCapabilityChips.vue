<script setup lang="ts">
import type { LlmCapability } from "@/types/llmModel";

defineProps<{ capabilities: LlmCapability[] }>();
</script>

<template>
  <ul v-if="capabilities.length" class="capability-chips" aria-label="Capacités">
    <li v-for="capability in capabilities" :key="capability.id" class="capability-chips__chip">
      {{ capability.name }}
    </li>
  </ul>
  <p v-else class="capability-chips__none">Aucune capacité</p>
</template>

<style scoped>
.capability-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.capability-chips__chip {
  padding: 0.125rem 0.625rem;
  border-radius: 999px;
  background: var(--background-contrast-grey, #eee);
  color: var(--text-mention-grey, #666);
  font-size: 0.8125rem;
}

.capability-chips__none {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--text-mention-grey, #666);
}
</style>
