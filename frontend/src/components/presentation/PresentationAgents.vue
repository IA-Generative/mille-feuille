<script setup lang="ts">
import MarkdownText from "@/components/MarkdownText.vue";
import type { PresentationAgent } from "@/types/dossierPresentation";

defineProps<{ agents: PresentationAgent[] }>();
</script>

<template>
  <ul class="presentation-agents">
    <li v-for="agent in agents" :key="agent.name" class="presentation-agents__item">
      <p class="presentation-agents__name">
        <VIcon name="ri-robot-2-line" aria-hidden="true" />
        {{ agent.name }}
      </p>
      <MarkdownText :content="agent.output" class="presentation-agents__output" />
    </li>
  </ul>
</template>

<style scoped>
.presentation-agents {
  display: grid;
  gap: 1rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.presentation-agents__name {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin: 0 0 0.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-mention-grey);
}

.presentation-agents__output {
  font-size: 0.9375rem;
}
</style>
