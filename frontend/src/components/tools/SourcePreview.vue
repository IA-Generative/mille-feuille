<script setup lang="ts">
import { computed, ref, watch } from "vue";

import type { ExternalBox } from "@/types/knowledge";

// L'aperçu d'une source : l'image de la page (ou la capture du site), avec le passage surligné quand on connaît ses
// zones (coordonnées normalisées 0..1). C'est un lien (source externe) ou un bouton (page du dossier, qui ouvre la modale).
// `src` vaut null tant que la capture n'est pas prête (ou n'existe pas) : on affiche alors l'espace réservé.
const props = defineProps<{ src: string | null ; boxes: ExternalBox[]; label: string; href?: string | null }>();
const emit = defineEmits<{ open: [] }>();

const failed = ref(false);
watch(() => props.src, () => (failed.value = false));
const showImage = computed(() => Boolean(props.src) && !failed.value);

const percent = (value: number) => `${(value * 100).toFixed(2)}%`;
</script>

<template>
  <component
    :is="href ? 'a' : 'button'"
    class="source-preview"
    :href="href || undefined"
    :target="href ? '_blank' : undefined"
    :rel="href ? 'noopener noreferrer' : undefined"
    :type="href ? undefined : 'button'"
    :aria-label="label"
    @click="!href && emit('open')"
  >
    <template v-if="showImage">
      <img class="source-preview__image" :src="src!" alt="" loading="lazy" referrerpolicy="no-referrer" @error="failed = true" />
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
    </template>
    <VIcon v-else name="ri-file-text-line" class="source-preview__placeholder" aria-hidden="true" />
  </component>
</template>

<style scoped>
.source-preview {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 7rem;
  aspect-ratio: 1 / 1.414; /* hauteur réservée dès le départ : la carte ne bouge ni à l'arrivée ni à l'échec de l'image */
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
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: top; /* une capture de site plus haute que la page est coupée par le bas, pas centrée */
}

.source-preview__placeholder {
  color: var(--text-mention-grey); /* jeton DSFR : contraste correct en thème clair et sombre */
}

.source-preview__box {
  position: absolute;
  background: color-mix(in srgb, var(--border-plain-yellow-tournesol) 35%, transparent);
  outline: 1px solid var(--border-plain-yellow-tournesol);
  pointer-events: none;
}
</style>
