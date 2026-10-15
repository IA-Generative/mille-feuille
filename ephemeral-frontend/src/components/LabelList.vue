<script setup lang="ts">
import type { LabelResult } from "@/types";

defineProps<{ labels: LabelResult[]; filtering: boolean }>();

const SOURCES: Record<string, string> = { textual: "Texte", visual: "Visuel" };
const percent = (c: number | null) => (c == null ? "" : `${Math.round(c * 100)} %`);
</script>

<template>
  <ul class="labels">
    <li v-for="(label, i) in labels" :key="label.prediction_id ?? i" class="label">
      <strong>{{ label.name }}</strong>
      <small class="muted">{{ percent(label.confidence) }} · {{ SOURCES[label.source] ?? label.source }}</small>
    </li>
    <li v-if="!labels.length" class="empty fr-text--sm muted">
      {{ filtering ? "Aucune classification de cette page ne correspond." : "Cette page n'a pas (encore) été classée." }}
    </li>
  </ul>
</template>

<style scoped>
.labels {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.label {
  display: flex;
  flex-direction: column;
  padding: 0.6rem 0.9rem;
  border-radius: 0.75rem;
  background: var(--background-alt-grey);
  overflow-wrap: anywhere;
}
.muted {
  color: var(--text-mention-grey);
}
.empty {
  padding: 1rem 0;
}
</style>
