<script setup lang="ts">
import { ref, watch } from "vue";

import type { ExternalBox } from "@/types/knowledge";

// L'aperçu d'une source : l'image de la page (ou la capture du site), avec le passage surligné quand on connaît ses
// zones (coordonnées normalisées 0..1). C'est un lien (source externe) ou un bouton (page du dossier, qui ouvre la modale).
const props = defineProps<{ src: string; boxes: ExternalBox[]; label: string; href?: string | null }>();
const emit = defineEmits<{ open: [] }>();

const failed = ref(false);
watch(() => props.src, () => (failed.value = false));

const percent = (value: number) => `${(value * 100).toFixed(2)}%`;
</script>

<template>
  <component
    :is="href ? 'a' : 'button'"
    v-if="!failed"
    class="source-preview"
    :href="href || undefined"
    :target="href ? '_blank' : undefined"
    :rel="href ? 'noopener noreferrer' : undefined"
    :type="href ? undefined : 'button'"
    :aria-label="label"
    @click="!href && emit('open')"
  >
    <img class="source-preview__image" :src="src" alt="" loading="lazy" referrerpolicy="no-referrer" @error="failed = true" />
    <span
      v-for="(box, index) in boxes"
      :key="index"
      class="source-preview__box"
      :style="{
        left: percent(box.xMin),
        top: percent(box.yMin),
        width: percent(box.xMax - box.xMin),
        height: percent(box.yMax - box.yMin),
      }"
    />
  </component>
</template>

<style scoped>
.source-preview {
  position: relative;
  display: block;
  flex-shrink: 0;
  width: 7rem;
  align-self: flex-start;
  padding: 0;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  overflow: hidden;
  background: var(--background-alt-grey);
  background-image: none;
  cursor: pointer;
}

.source-preview:focus-visible {
  outline: 2px solid #6a5cff;
  outline-offset: 2px;
}

/* L'icône de lien externe que le thème ajoute aux liens qui s'ouvrent dans un autre onglet n'a rien à faire ici. */
.source-preview::after {
  content: none;
  display: none;
}

.source-preview__image {
  display: block;
  width: 100%;
  height: auto;
}

.source-preview__box {
  position: absolute;
  background: #ffd60a59;
  outline: 1px solid #ffd60a;
  pointer-events: none;
}
</style>
