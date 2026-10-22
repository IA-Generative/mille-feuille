<script setup lang="ts">
import { computed, ref } from "vue";

import type { ExternalSource } from "@/types/knowledge";

// L'aperçu d'une source : l'image de la page (ou la capture du site) fournie par la base de connaissances, avec le
// passage surligné quand le fournisseur donne des zones. Les zones sont en coordonnées normalisées 0..1.
const props = defineProps<{ source: ExternalSource }>();

const failed = ref(false);

// Les zones d'une autre page que celle de l'aperçu ne se superposent pas à l'image.
const boxes = computed(() =>
  props.source.boxes.filter((box) => props.source.page === null || box.page === props.source.page),
);

const percent = (value: number) => `${(value * 100).toFixed(2)}%`;
</script>

<template>
  <a
    v-if="source.previewUrl && !failed"
    class="external-preview"
    :href="source.url"
    target="_blank"
    rel="noopener noreferrer"
    :aria-label="`Ouvrir la source « ${source.title} »`"
  >
    <img
      class="external-preview__image"
      :src="source.previewUrl"
      alt=""
      loading="lazy"
      referrerpolicy="no-referrer"
      @error="failed = true"
    />
    <span
      v-for="(box, index) in boxes"
      :key="index"
      class="external-preview__box"
      :style="{
        left: percent(box.xMin),
        top: percent(box.yMin),
        width: percent(box.xMax - box.xMin),
        height: percent(box.yMax - box.yMin),
      }"
    />
  </a>
</template>

<style scoped>
.external-preview {
  position: relative;
  display: block;
  flex-shrink: 0;
  width: 7rem;
  align-self: flex-start;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  overflow: hidden;
  background: var(--background-alt-grey);
  background-image: none;
}

/* L'icône de lien externe que le thème ajoute aux liens qui s'ouvrent dans un autre onglet n'a rien à faire ici. */
.external-preview::after {
  content: none;
  display: none;
}

.external-preview__image {
  display: block;
  width: 100%;
  height: auto;
}

.external-preview__box {
  position: absolute;
  background: #ffd60a59;
  outline: 1px solid #ffd60a;
  pointer-events: none;
}
</style>
