<script setup lang="ts">
import { computed, toRef } from "vue";

import SourcePreview from "@/components/tools/SourcePreview.vue";
import { useDossierPageImage } from "@/composables/useDossierPageImage";
import type { ChatSource } from "@/types/chatSource";

// Une source citée par la réponse : la même carte pour une page du dossier et pour une base de connaissances externe.
const props = defineProps<{ source: ChatSource; dossierId: string }>();
const emit = defineEmits<{ open: [source: ChatSource] }>();

const { url: pageImage } = useDossierPageImage(
  toRef(props, "dossierId"),
  computed(() => (props.source.dossier ? { documentId: props.source.dossier.documentId, pageId: props.source.dossier.pageId } : null)),
);

const previewSrc = computed(() => props.source.previewUrl ?? pageImage.value);
const kindLabel = computed(() => (props.source.origin === "dossier" ? "Dossier" : props.source.kind === "web" ? "Site web" : "Document"));
const meta = computed(() => [kindLabel.value, props.source.pageLabel, props.source.context].filter(Boolean).join(" · "));
</script>

<template>
  <article class="source-card">
    <SourcePreview
      v-if="previewSrc"
      :src="previewSrc"
      :boxes="source.boxes"
      :href="source.url"
      :label="`Ouvrir la source ${source.number} : ${source.title}`"
      @open="emit('open', source)"
    />
    <div class="source-card__body">
      <p class="source-card__title">
        <span class="source-card__number">[{{ source.number }}]</span>
        <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.title }}</a>
        <button v-else type="button" class="source-card__link" @click="emit('open', source)">{{ source.title }}</button>
      </p>
      <p class="source-card__meta">{{ meta }}</p>
      <p v-if="source.passage" class="source-card__passage">« {{ source.passage }} »</p>
    </div>
  </article>
</template>

<style scoped>
.source-card {
  display: flex;
  gap: 0.75rem;
  height: 100%;
  padding: 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
  background: var(--background-default-grey);
  box-sizing: border-box;
}

.source-card__body {
  min-width: 0;
  flex: 1;
}

.source-card__title,
.source-card__meta,
.source-card__passage {
  margin: 0;
}

.source-card__title {
  font-weight: 600;
  overflow-wrap: anywhere;
}

.source-card__number {
  margin-right: 0.375rem;
  color: #4b3fd9;
}

.source-card__link {
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-weight: 600;
  color: var(--text-action-high-blue-france);
  text-align: left;
  text-decoration: underline;
  cursor: pointer;
}

.source-card__meta {
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.source-card__passage {
  display: -webkit-box;
  margin-top: 0.375rem;
  font-size: 0.8125rem;
  overflow: hidden;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
}
</style>
