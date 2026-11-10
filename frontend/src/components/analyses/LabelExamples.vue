<script setup lang="ts">
import { ref } from "vue";

import {
  EXAMPLE_ACCEPT,
  MAX_EXAMPLES_PER_LABEL,
  MAX_EXAMPLE_SIZE,
  formatSize,
  useLabelExamples,
} from "@/composables/useLabelExamples";

const props = defineProps<{ labelId: string }>();

const { examplesOf, addFiles, removeExample } = useLabelExamples();
const examples = examplesOf(props.labelId);

const input = ref<HTMLInputElement | null>(null);
const isDragging = ref(false);
const errors = ref<string[]>([]);

function receive(files: FileList | null) {
  if (!files || files.length === 0) return;
  errors.value = addFiles(props.labelId, Array.from(files));
}

function onChange(event: Event) {
  const target = event.target as HTMLInputElement;
  receive(target.files);
  target.value = "";
}

function onDrop(event: DragEvent) {
  isDragging.value = false;
  receive(event.dataTransfer?.files ?? null);
}
</script>

<template>
  <div class="label-examples">
    <p class="label-examples__title">Documents d'exemple</p>
    <p class="fr-hint-text label-examples__hint">
      Ajoutez des PDF ou des images qui ressemblent aux pages de ce label : la classification visuelle les compare aux pages du
      dossier, en plus de la définition.
    </p>

    <button
      type="button"
      class="label-examples__drop"
      :class="{ 'label-examples__drop--active': isDragging }"
      @click="input?.click()"
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @drop.prevent="onDrop"
    >
      <VIcon name="ri-upload-2-line" aria-hidden="true" />
      <span class="label-examples__drop-main">Déposer des fichiers ou <u>parcourir</u></span>
      <span class="label-examples__drop-hint">
        PDF, PNG, JPEG ou WebP · {{ formatSize(MAX_EXAMPLE_SIZE) }} maximum · {{ MAX_EXAMPLES_PER_LABEL }} exemples par label
      </span>
    </button>
    <input ref="input" class="label-examples__input" type="file" multiple :accept="EXAMPLE_ACCEPT" tabindex="-1" @change="onChange" />

    <ul v-if="errors.length > 0" class="label-examples__errors" role="alert">
      <li v-for="error in errors" :key="error">{{ error }}</li>
    </ul>

    <ul v-if="examples.length > 0" class="label-examples__list">
      <li v-for="example in examples" :key="example.id" class="label-examples__item">
        <img v-if="example.previewUrl" :src="example.previewUrl" alt="" class="label-examples__thumb" />
        <span v-else class="label-examples__thumb label-examples__thumb--pdf" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
            <path d="M14 3v5h5M9 13h6M9 17h6" />
          </svg>
        </span>
        <span class="label-examples__meta">
          <span class="label-examples__name" :title="example.name">{{ example.name }}</span>
          <span class="label-examples__size">{{ example.kind === "pdf" ? "PDF" : "Image" }} · {{ formatSize(example.size) }}</span>
        </span>
        <DsfrButton
          :label="`Retirer ${example.name}`"
          icon-only
          tertiary
          no-outline
          icon="ri-close-line"
          size="sm"
          @click="removeExample(labelId, example.id)"
        />
      </li>
    </ul>
    <p v-else class="label-examples__empty">Aucun exemple : seule la définition est utilisée.</p>
  </div>
</template>

<style scoped>
.label-examples {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.label-examples__title {
  margin: 0;
  font-weight: 600;
}

.label-examples__hint {
  margin: 0;
}

.label-examples__drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 1rem;
  border: 1px dashed var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-default-grey);
  color: inherit;
  cursor: pointer;
  text-align: center;
}

.label-examples__drop:hover,
.label-examples__drop--active {
  border-color: #6a5cff;
  background: var(--background-alt-grey);
}

.label-examples__drop-hint,
.label-examples__size,
.label-examples__empty {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.label-examples__input {
  display: none;
}

.label-examples__errors {
  margin: 0;
  padding-left: 1.25rem;
  font-size: 0.875rem;
  color: var(--text-default-error);
}

.label-examples__empty {
  margin: 0;
}

.label-examples__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
  gap: 0.5rem;
}

.label-examples__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.5rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
}

.label-examples__thumb {
  width: 2.5rem;
  height: 3.25rem;
  flex-shrink: 0;
  object-fit: cover;
  border-radius: 0.25rem;
  background: var(--background-alt-grey);
}

.label-examples__thumb--pdf {
  display: flex;
  align-items: center;
  justify-content: center;
}

.label-examples__meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.label-examples__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.875rem;
}
</style>
