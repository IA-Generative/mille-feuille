<script setup lang="ts">
import { ref } from "vue";

const file = defineModel<File | null>({ required: true });
const over = ref(false);

const pick = (list: FileList | null) => {
  if (list?.length) file.value = list[0];
};
const onDrop = (event: DragEvent) => {
  over.value = false;
  pick(event.dataTransfer?.files ?? null);
};
const size = (bytes: number) => (bytes > 1e6 ? `${(bytes / 1e6).toFixed(1)} Mo` : `${Math.ceil(bytes / 1e3)} Ko`);
</script>

<template>
  <label
    class="dropzone"
    :class="{ over, filled: file }"
    @dragover.prevent="over = true"
    @dragleave="over = false"
    @drop.prevent="onDrop"
  >
    <input type="file" class="sr" @change="pick(($event.target as HTMLInputElement).files)" />
    <span class="fr-icon-upload-2-line fr-icon--lg" aria-hidden="true"></span>
    <template v-if="file">
      <strong>{{ file.name }}</strong>
      <span class="fr-text--sm">{{ size(file.size) }} · cliquer pour changer</span>
    </template>
    <template v-else>
      <strong>Déposez un document ici</strong>
      <span class="fr-text--sm">ou cliquez pour le choisir (PDF, image…)</span>
    </template>
  </label>
</template>

<style scoped>
.dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2.5rem 1rem;
  border: 2px dashed var(--border-default-grey);
  border-radius: 0.75rem;
  cursor: pointer;
  text-align: center;
  transition: background 0.15s, border-color 0.15s;
}
.dropzone:hover,
.dropzone.over {
  background: var(--background-alt-blue-france);
  border-color: var(--border-action-high-blue-france);
}
.dropzone.filled {
  border-style: solid;
}
.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}
</style>
