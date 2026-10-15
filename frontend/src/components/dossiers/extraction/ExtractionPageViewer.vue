<script setup lang="ts">
import type { ExtractionBox } from "@/types/dossierExtraction";

/** Image d'une page avec des rectangles numérotés par-dessus. `active` : indice du groupe mis en avant. */
defineProps<{
  src: string;
  alt: string;
  groups: { label: string; boxes: ExtractionBox[] }[];
  active: number | null;
}>();

const style = (box: ExtractionBox) => ({
  left: `${box.xMin * 100}%`,
  top: `${box.yMin * 100}%`,
  width: `${(box.xMax - box.xMin) * 100}%`,
  height: `${(box.yMax - box.yMin) * 100}%`,
});
</script>

<template>
  <div class="extraction-viewer">
    <img :src="src" :alt="alt" class="extraction-viewer__image" />
    <template v-for="(group, index) in groups" :key="index">
      <span
        v-for="(box, i) in group.boxes"
        :key="i"
        class="extraction-viewer__box"
        :class="{
          'extraction-viewer__box--active': active === index,
          'extraction-viewer__box--dim': active !== null && active !== index,
        }"
        :style="style(box)"
        aria-hidden="true"
      >
        <span v-if="i === 0" class="extraction-viewer__tag">{{ group.label }}</span>
      </span>
    </template>
  </div>
</template>

<style scoped>
.extraction-viewer {
  position: relative;
  display: inline-block;
  max-width: 100%;
  line-height: 0;
  border-radius: 0.5rem;
  overflow: hidden;
  border: 1px solid var(--border-default-grey);
}

.extraction-viewer__image {
  display: block;
  max-width: 100%;
  height: auto;
}

.extraction-viewer__box {
  position: absolute;
  box-sizing: border-box;
  border: 2px solid var(--border-action-high-blue-france);
  background: color-mix(in srgb, var(--background-action-high-blue-france) 12%, transparent);
  border-radius: 2px;
  transition: opacity 0.15s;
}

.extraction-viewer__box--active {
  border-width: 3px;
  background: color-mix(in srgb, var(--background-action-high-blue-france) 28%, transparent);
}

.extraction-viewer__box--dim {
  opacity: 0.35;
}

.extraction-viewer__tag {
  position: absolute;
  left: -2px;
  top: -1.2rem;
  padding: 0 0.3rem;
  font-size: 0.7rem;
  line-height: 1.1rem;
  color: #fff;
  background: var(--background-action-high-blue-france);
  border-radius: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .extraction-viewer__box {
    transition: none;
  }
}
</style>
