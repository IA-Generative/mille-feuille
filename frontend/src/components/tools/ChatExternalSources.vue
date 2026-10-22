<script setup lang="ts">
import ExternalSourceCard from "@/components/tools/ExternalSourceCard.vue";
import type { ExternalSource } from "@/types/knowledge";

// Les sources d'une base de connaissances externe que la réponse cite, numérotées comme dans le texte ([1], [2]…).
defineProps<{ sources: ExternalSource[] }>();
</script>

<template>
  <details v-if="sources.length > 0" class="chat-external-sources" open>
    <summary class="chat-external-sources__summary">
      <VIcon name="ri-book-2-line" scale="0.85" /> Sources de la base de connaissances ({{ sources.length }})
    </summary>
    <ul class="chat-external-sources__list">
      <ExternalSourceCard v-for="(source, index) in sources" :key="source.sourceId" :source="source" :number="index + 1" />
    </ul>
  </details>
</template>

<style scoped>
.chat-external-sources {
  margin-top: 0.5rem;
  width: min(100%, 40rem);
}

.chat-external-sources__summary {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
  cursor: pointer;
}

.chat-external-sources__list {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
</style>
