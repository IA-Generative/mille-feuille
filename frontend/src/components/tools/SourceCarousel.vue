<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import SourceCard from "@/components/tools/SourceCard.vue";
import type { ChatSource } from "@/types/chatSource";

// Les sources d'une réponse : une carte, ou un carrousel quand il y en a plusieurs (défilement au toucher et à la
// molette, flèches, clavier). Un clic sur un numéro du texte ([2]) envoie `goto-source` à ce bloc, qui se place sur la
// bonne carte.
const props = defineProps<{ sources: ChatSource[]; dossierId: string; messageId: string }>();
const emit = defineEmits<{ open: [source: ChatSource] }>();

const root = ref<HTMLElement>();
const track = ref<HTMLElement>();
const current = ref(0);
const flash = ref(false);

const many = computed(() => props.sources.length > 1);
const prefersReducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
const slides = () => Array.from(track.value?.children ?? []) as HTMLElement[];

function goTo(index: number) {
  const slide = slides()[Math.min(Math.max(index, 0), props.sources.length - 1)];
  if (!slide || !track.value) return;
  current.value = slides().indexOf(slide);
  track.value.scrollTo({ left: slide.offsetLeft - track.value.offsetLeft, behavior: prefersReducedMotion() ? "auto" : "smooth" });
}

// La carte la plus proche du bord gauche est la courante (la personne peut aussi faire défiler au toucher).
let frame = 0;
function onScroll() {
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(() => {
    const left = track.value?.scrollLeft ?? 0;
    const offset = track.value?.offsetLeft ?? 0;
    let best = 0;
    slides().forEach((slide, index) => {
      if (Math.abs(slide.offsetLeft - offset - left) < Math.abs(slides()[best].offsetLeft - offset - left)) best = index;
    });
    current.value = best;
  });
}

function onGoto(event: Event) {
  const number = (event as CustomEvent<number>).detail;
  const index = props.sources.findIndex((source) => source.number === number);
  if (index === -1) return;
  root.value?.scrollIntoView({ block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  goTo(index);
  flash.value = true;
  setTimeout(() => (flash.value = false), 1200);
}

function onKeydown(event: KeyboardEvent) {
  if (!many.value || (event.target as HTMLElement).closest("input, textarea")) return;
  if (event.key === "ArrowRight") goTo(current.value + 1);
  else if (event.key === "ArrowLeft") goTo(current.value - 1);
  else return;
  event.preventDefault();
}

onMounted(() => root.value?.addEventListener("goto-source", onGoto));
onBeforeUnmount(() => {
  root.value?.removeEventListener("goto-source", onGoto);
  cancelAnimationFrame(frame);
});
</script>

<template>
  <section
    :id="`sources-${messageId}`"
    ref="root"
    class="source-carousel"
    :class="{ 'source-carousel--flash': flash }"
    role="region"
    aria-roledescription="carousel"
    :aria-label="many ? `Sources de la réponse (${sources.length})` : 'Source de la réponse'"
    @keydown="onKeydown"
  >
    <header class="source-carousel__header">
      <span class="source-carousel__title"><VIcon name="ri-book-2-line" scale="0.85" /> {{ many ? `Sources (${sources.length})` : "Source" }}</span>
      <div v-if="many" class="source-carousel__nav">
        <span class="source-carousel__count" aria-live="polite">{{ current + 1 }} / {{ sources.length }}</span>
        <button type="button" class="source-carousel__button" aria-label="Source précédente" :disabled="current === 0" @click="goTo(current - 1)">
          <VIcon name="ri-arrow-left-s-line" />
        </button>
        <button
          type="button"
          class="source-carousel__button"
          aria-label="Source suivante"
          :disabled="current === sources.length - 1"
          @click="goTo(current + 1)"
        >
          <VIcon name="ri-arrow-right-s-line" />
        </button>
      </div>
    </header>
    <ul ref="track" class="source-carousel__track" :class="{ 'source-carousel__track--many': many }" @scroll.passive="onScroll">
      <li
        v-for="(source, index) in sources"
        :key="source.key"
        class="source-carousel__slide"
        role="group"
        aria-roledescription="slide"
        :aria-label="`${index + 1} sur ${sources.length}`"
      >
        <SourceCard :source="source" :dossier-id="dossierId" @open="emit('open', $event)" />
      </li>
    </ul>
  </section>
</template>

<style scoped>
.source-carousel {
  margin-top: 0.5rem;
  width: min(100%, 40rem);
  border-radius: 0.75rem;
  transition: box-shadow 0.3s ease;
}

.source-carousel--flash {
  box-shadow: 0 0 0 3px #6a5cff55;
}

.source-carousel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.375rem;
}

.source-carousel__title {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.source-carousel__nav {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.source-carousel__count {
  margin-right: 0.25rem;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.source-carousel__button {
  display: inline-flex;
  padding: 0.25rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 50%;
  background: var(--background-default-grey);
  color: inherit;
  cursor: pointer;
}

.source-carousel__button:disabled {
  opacity: 0.4;
  cursor: default;
}

.source-carousel__button:focus-visible {
  outline: 2px solid #6a5cff;
  outline-offset: 2px;
}

.source-carousel__track {
  display: flex;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scrollbar-width: none;
}

.source-carousel__track::-webkit-scrollbar {
  display: none;
}

.source-carousel__slide {
  flex: 0 0 100%;
  min-width: 0;
  scroll-snap-align: start;
}

/* On entrevoit la carte suivante : c'est ce qui dit qu'on peut faire défiler. */
.source-carousel__track--many .source-carousel__slide {
  flex-basis: 88%;
}

@media (prefers-reduced-motion: reduce) {
  .source-carousel {
    transition: none;
  }
}
</style>
