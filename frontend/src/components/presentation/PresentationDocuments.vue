<script setup lang="ts">
import type { PresentationDocument } from "@/types/dossierPresentation";

defineProps<{ documents: PresentationDocument[] }>();
</script>

<template>
  <ul class="presentation-documents">
    <li v-for="document in documents" :key="document.id" class="presentation-documents__item">
      <VIcon name="ri-file-text-line" aria-hidden="true" />
      <span class="presentation-documents__name">{{ document.name }}</span>
      <span v-if="document.label" class="presentation-documents__label">{{ document.label }}</span>
      <span class="presentation-documents__pages">
        {{ document.pageCount }} {{ document.pageCount > 1 ? "pages" : "page" }}
      </span>
    </li>
  </ul>
</template>

<style scoped>
.presentation-documents {
  display: grid;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.presentation-documents__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
  font-size: 0.9375rem;
}

.presentation-documents__name {
  overflow-wrap: anywhere;
}

.presentation-documents__label {
  padding: 0.0625rem 0.5rem;
  border-radius: 999px;
  background: var(--background-contrast-grey);
  font-size: 0.75rem;
}

.presentation-documents__pages {
  margin-left: auto;
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}
</style>
