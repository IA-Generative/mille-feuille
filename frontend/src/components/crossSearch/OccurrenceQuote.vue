<script setup lang="ts">
/** Un extrait et le document d'où il vient. */
import type { Excerpt, Occurrence } from "@/types/crossSearch";

defineProps<{ excerpt: Excerpt & Partial<Pick<Occurrence, "origin">> }>();
</script>

<template>
  <blockquote class="occurrence">
    {{ excerpt.text }}
    <footer>{{ excerpt.documentName }}, page {{ excerpt.page }}</footer>
    <footer v-if="excerpt.origin">Entité : {{ excerpt.origin }}</footer>
  </blockquote>
</template>

<style scoped>
.occurrence {
  margin: 0;
  padding-left: 0.75rem;
  border-left: 3px solid var(--border-default-grey);
  font-size: 0.875rem;
}

.occurrence footer {
  color: var(--text-mention-grey);
  font-size: 0.75rem;
}
</style>
