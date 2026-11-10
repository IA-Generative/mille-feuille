<script setup lang="ts">
import { computed, ref } from "vue";

import type { ZoneRect } from "@/composables/useEntityLocations";

/** Ce que couvre la zone : la page découpée à son rectangle (rien d'autre n'est chargé que la page elle-même). */
const props = defineProps<{ url: string; rect: ZoneRect }>();

const ratio = ref<number | null>(null);

function onLoad(event: Event) {
  const img = event.target as HTMLImageElement;
  if (img.naturalHeight) ratio.value = img.naturalWidth / img.naturalHeight;
}

const w = computed(() => Math.max(props.rect.x1 - props.rect.x0, 0.005));
const h = computed(() => Math.max(props.rect.y1 - props.rect.y0, 0.005));

// La zone est en fractions de la page : sa forme à l'écran dépend des proportions de la page.
const frameStyle = computed(() => {
  if (!ratio.value) return { display: "none" };
  const aspect = (w.value * ratio.value) / h.value;
  return { aspectRatio: String(aspect), width: `min(11rem, ${2.5 * aspect}rem)` };
});
const imageStyle = computed(() => ({
  width: `${100 / w.value}%`,
  left: `${(-props.rect.x0 / w.value) * 100}%`,
  top: `${(-props.rect.y0 / h.value) * 100}%`,
}));
</script>

<template>
  <div class="zone-crop" :style="frameStyle">
    <img :src="url" alt="Aperçu de la zone" class="zone-crop__image" :style="imageStyle" @load="onLoad" />
  </div>
</template>

<style scoped>
.zone-crop {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border-default-grey);
  background: var(--background-contrast-grey);
}

.zone-crop__image {
  position: absolute;
  max-width: none;
  height: auto;
}
</style>
