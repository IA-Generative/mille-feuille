<script setup lang="ts">
import { nextTick, useTemplateRef } from "vue";

// Fichiers choisis avant l'envoi (création d'un dossier, ajout de documents), avec un bouton pour retirer chacun.
// `focusOnEmpty` : id de l'élément qui reçoit le focus quand le dernier fichier est retiré (le champ de dépôt).
const props = defineProps<{ files: File[]; focusOnEmpty?: string }>();
const emit = defineEmits<{ remove: [index: number] }>();

const list = useTemplateRef<HTMLUListElement>("list");

function formatSize(bytes: number) {
  return bytes < 1_000_000 ? `${Math.round(bytes / 1000)} Ko` : `${(bytes / 1_000_000).toFixed(1)} Mo`;
}

// Le bouton cliqué disparaît avec son fichier : sans cela, le focus tomberait sur la page.
async function remove(index: number) {
  emit("remove", index);
  await nextTick();
  if (props.files.length === 0) {
    if (props.focusOnEmpty) document.getElementById(props.focusOnEmpty)?.focus();
    return;
  }
  const buttons = list.value?.querySelectorAll<HTMLButtonElement>("button");
  buttons?.[Math.min(index, props.files.length - 1)]?.focus();
}
</script>

<template>
  <ul v-if="files.length > 0" ref="list" class="fr-raw-list fr-mt-2w">
    <li
      v-for="(file, index) in files"
      :key="`${file.name}-${index}`"
      class="fr-grid-row fr-grid-row--middle fr-grid-row--gutters fr-mb-1w"
    >
      <span class="fr-col fr-text--sm fr-mb-0">{{ file.name }} ({{ formatSize(file.size) }})</span>
      <DsfrButton
        :label="`Retirer le fichier ${file.name}`"
        icon-only
        tertiary
        no-outline
        icon="ri-close-line"
        size="sm"
        @click="remove(index)"
      />
    </li>
  </ul>
</template>
