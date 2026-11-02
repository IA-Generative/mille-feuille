<script setup lang="ts">
/**
 * Texte limité à `lines` lignes avec « Voir plus / Voir moins » : les définitions générées par le LLM peuvent être
 * longues. Le bouton n'apparaît que si le texte est réellement tronqué.
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = withDefaults(defineProps<{ text: string; lines?: number }>(), { lines: 2 });

const textRef = ref<HTMLElement | null>(null);
const expanded = ref(false);
const overflowing = ref(false);

function measure() {
  const el = textRef.value;
  if (el && !expanded.value) overflowing.value = el.scrollHeight > el.clientHeight + 1;
}

let observer: ResizeObserver | null = null;
onMounted(() => {
  measure();
  if (textRef.value && typeof ResizeObserver !== "undefined") {
    observer = new ResizeObserver(measure);
    observer.observe(textRef.value);
  }
});
onBeforeUnmount(() => observer?.disconnect());
watch(() => props.text, () => nextTick(measure));
</script>

<template>
  <div class="collapsible-text">
    <p
      ref="textRef"
      class="fr-text--sm collapsible-text__body"
      :class="{ 'collapsible-text__body--clamped': !expanded }"
      :style="{ '--lines': lines }"
    >
      {{ text }}
    </p>
    <button v-if="overflowing || expanded" type="button" class="collapsible-text__toggle" :aria-expanded="expanded" @click="expanded = !expanded">
      {{ expanded ? "Voir moins" : "Voir plus" }}
    </button>
  </div>
</template>

<style scoped>
.collapsible-text__body {
  margin: 0.25rem 0 0;
  color: var(--text-mention-grey);
  overflow-wrap: anywhere;
}

.collapsible-text__body--clamped {
  display: -webkit-box;
  -webkit-line-clamp: var(--lines);
  line-clamp: var(--lines);
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.collapsible-text__toggle {
  padding: 0;
  border: none;
  background: none;
  color: var(--text-action-high-blue-france);
  font-size: 0.8125rem;
  cursor: pointer;
  text-decoration: underline;
}
</style>
