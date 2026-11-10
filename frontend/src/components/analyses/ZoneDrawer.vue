<script setup lang="ts">
import { computed, ref } from "vue";

import type { ZoneRect } from "@/composables/useEntityLocations";

defineProps<{ url: string; rects: ZoneRect[] }>();
const emit = defineEmits<{ add: [ZoneRect] }>();

const MIN_SIDE = 0.01;

const frame = ref<HTMLElement | null>(null);
const start = ref<{ x: number; y: number } | null>(null);
const live = ref<ZoneRect | null>(null);

const clamp = (n: number) => Math.min(Math.max(n, 0), 1);

function point(event: PointerEvent) {
  const box = frame.value!.getBoundingClientRect();
  return { x: clamp((event.clientX - box.left) / box.width), y: clamp((event.clientY - box.top) / box.height) };
}

function rectBetween(a: { x: number; y: number }, b: { x: number; y: number }): ZoneRect {
  return { x0: Math.min(a.x, b.x), y0: Math.min(a.y, b.y), x1: Math.max(a.x, b.x), y1: Math.max(a.y, b.y) };
}

function onDown(event: PointerEvent) {
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  start.value = point(event);
  live.value = null;
}

function onMove(event: PointerEvent) {
  if (start.value) live.value = rectBetween(start.value, point(event));
}

function onUp() {
  const drawn = live.value;
  start.value = null;
  live.value = null;
  // Un simple clic ne dessine rien.
  if (drawn && drawn.x1 - drawn.x0 >= MIN_SIDE && drawn.y1 - drawn.y0 >= MIN_SIDE) emit("add", drawn);
}

function styleOf(r: ZoneRect) {
  return { left: `${r.x0 * 100}%`, top: `${r.y0 * 100}%`, width: `${(r.x1 - r.x0) * 100}%`, height: `${(r.y1 - r.y0) * 100}%` };
}
</script>

<template>
  <div
    ref="frame"
    class="zone-drawer"
    role="img"
    aria-label="Page du document : tracez un rectangle pour désigner la zone où se trouve l'information"
    @pointerdown.prevent="onDown"
    @pointermove="onMove"
    @pointerup="onUp"
    @pointercancel="onUp"
  >
    <img :src="url" alt="" class="zone-drawer__image" draggable="false" />
    <div v-for="(rect, index) in rects" :key="index" class="zone-drawer__zone" :style="styleOf(rect)">
      <span class="zone-drawer__number">{{ index + 1 }}</span>
    </div>
    <div v-if="live" class="zone-drawer__zone zone-drawer__zone--live" :style="styleOf(live)"></div>
  </div>
</template>

<style scoped>
.zone-drawer {
  position: relative;
  display: inline-block;
  max-width: 100%;
  line-height: 0;
  border: 1px solid var(--border-default-grey);
  cursor: crosshair;
  touch-action: none;
  user-select: none;
}

.zone-drawer__image {
  display: block;
  max-width: 100%;
  max-height: 22rem;
  pointer-events: none;
}

.zone-drawer__zone {
  position: absolute;
  border: 2px solid #9d6cff;
  background: rgba(157, 108, 255, 0.18);
  pointer-events: none;
}

.zone-drawer__zone--live {
  border-style: dashed;
}

.zone-drawer__number {
  position: absolute;
  top: 0;
  left: 0;
  min-width: 1.1rem;
  padding: 0 0.25rem;
  background: #9d6cff;
  color: #fff;
  font-size: 0.75rem;
  line-height: 1.1rem;
  text-align: center;
}
</style>
