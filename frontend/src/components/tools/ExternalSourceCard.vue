<script setup lang="ts">
import ExternalSourcePreview from "@/components/tools/ExternalSourcePreview.vue";
import type { ExternalSource } from "@/types/knowledge";

defineProps<{ source: ExternalSource; number: number }>();
</script>

<template>
  <li class="external-source">
    <ExternalSourcePreview :source="source" />
    <div class="external-source__body">
      <p class="external-source__title">
        <span class="external-source__number">[{{ number }}]</span>
        <a :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.title }}</a>
      </p>
      <p class="external-source__meta">
        {{ source.kind === "web" ? "Site web" : "Document" }}<template v-if="source.page"> · page {{ source.page }}</template>
        <template v-if="source.collectionName"> · {{ source.collectionName }}</template>
      </p>
      <p class="external-source__passage">« {{ source.passage }} »</p>
    </div>
  </li>
</template>

<style scoped>
.external-source {
  display: flex;
  gap: 0.75rem;
  padding: 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
  background: var(--background-default-grey);
}

.external-source__body {
  min-width: 0;
  flex: 1;
}

.external-source__title,
.external-source__meta,
.external-source__passage {
  margin: 0;
}

.external-source__title {
  font-weight: 600;
  overflow-wrap: anywhere;
}

.external-source__number {
  margin-right: 0.375rem;
  color: #4b3fd9;
}

.external-source__meta {
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.external-source__passage {
  display: -webkit-box;
  margin-top: 0.375rem;
  font-size: 0.8125rem;
  overflow: hidden;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
}
</style>
