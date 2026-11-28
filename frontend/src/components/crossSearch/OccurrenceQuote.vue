<script setup lang="ts">
/** Un extrait et le document d'où il vient. */
import type { Excerpt, Occurrence } from "@/types/crossSearch";

defineProps<{ excerpt: Excerpt & Partial<Pick<Occurrence, "origin">> }>();

const place = ({ documentName, page }: Excerpt) =>
  [documentName, page ? `page ${page}` : null].filter(Boolean).join(", ");
</script>

<template>
  <blockquote class="occurrence">
    <template v-if="excerpt.segments">
      <template v-for="(segment, index) in excerpt.segments" :key="index">
        <mark v-if="segment.highlighted">{{ segment.text }}</mark>
        <template v-else>{{ segment.text }}</template>
      </template>
    </template>
    <template v-else>{{ excerpt.text }}</template>
    <footer v-if="excerpt.field">Valeur : {{ excerpt.field }}</footer>
    <footer v-if="place(excerpt)">{{ place(excerpt) }}</footer>
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
