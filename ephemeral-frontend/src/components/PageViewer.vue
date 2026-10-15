<script setup lang="ts">
import type { Box } from "@/types";

/** Image d'une page avec des rectangles par-dessus (coordonnées normalisées). `active` : indices des groupes mis en avant. */
defineProps<{
  src: string;
  alt: string;
  groups: { label: string; boxes: Box[] }[];
  active: number | null;
}>();

const style = (box: Box) => ({
  left: `${box.x_min * 100}%`,
  top: `${box.y_min * 100}%`,
  width: `${(box.x_max - box.x_min) * 100}%`,
  height: `${(box.y_max - box.y_min) * 100}%`,
});
</script>

<template>
  <div class="viewer">
    <img :src="src" :alt="alt" />
    <template v-for="(group, index) in groups" :key="index">
      <span
        v-for="(box, i) in group.boxes"
        :key="i"
        class="box"
        :class="{ active: active === index, dim: active !== null && active !== index }"
        :style="style(box)"
        aria-hidden="true"
      >
        <span v-if="i === 0" class="tag">{{ group.label }}</span>
      </span>
    </template>
  </div>
</template>

<style scoped>
.viewer {
  position: relative;
  display: inline-block;
  max-width: 100%;
  line-height: 0;
  border-radius: 0.5rem;
  overflow: hidden;
  border: 1px solid var(--border-default-grey);
}
img {
  display: block;
  max-width: 100%;
  height: auto;
}
.box {
  position: absolute;
  box-sizing: border-box;
  border: 2px solid var(--border-action-high-blue-france);
  background: color-mix(in srgb, var(--background-action-high-blue-france) 12%, transparent);
  border-radius: 2px;
  transition: opacity 0.15s;
}
.box.active {
  border-width: 3px;
  background: color-mix(in srgb, var(--background-action-high-blue-france) 28%, transparent);
}
.box.dim {
  opacity: 0.35;
}
.tag {
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
  .box {
    transition: none;
  }
}
</style>
