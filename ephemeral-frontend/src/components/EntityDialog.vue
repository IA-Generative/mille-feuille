<script setup lang="ts">
/**
 * Une extraction en grand : la zone de la page autour de la valeur (rectangle un peu agrandi pour que le contexte se
 * lise) et la valeur en texte sélectionnable, avec un bouton pour la copier.
 */
import { computed, onMounted, ref } from "vue";

import CopyButton from "@/components/CopyButton.vue";
import { cropRegion } from "@/utils/crop";
import type { EntityResult } from "@/types";

const props = defineProps<{ entity: EntityResult; src?: string; pageNumber: number }>();
const emit = defineEmits<{ close: [] }>();

const SOURCES: Record<string, string> = { textual: "Texte", visual: "Visuel", gliner: "GLiNER" };

const dialog = ref<HTMLDialogElement | null>(null);
const natural = ref<{ width: number; height: number } | null>(null);

const region = computed(() => (props.entity.boxes.length ? cropRegion(props.entity.boxes) : null));
const width = computed(() => (region.value ? region.value.x_max - region.value.x_min : 1));
const height = computed(() => (region.value ? region.value.y_max - region.value.y_min : 1));

// Le cadre garde les proportions de la zone découpée ; l'image est agrandie et décalée pour que la zone le remplisse.
const ratio = computed(() =>
  natural.value ? (width.value * natural.value.width) / (height.value * natural.value.height) : 3,
);
const imageStyle = computed(() =>
  region.value
    ? {
        width: `${100 / width.value}%`,
        left: `${(-region.value.x_min / width.value) * 100}%`,
        top: `${(-region.value.y_min / height.value) * 100}%`,
      }
    : {},
);
const boxStyle = (box: EntityResult["boxes"][number]) => ({
  left: `${((box.x_min - region.value!.x_min) / width.value) * 100}%`,
  top: `${((box.y_min - region.value!.y_min) / height.value) * 100}%`,
  width: `${((box.x_max - box.x_min) / width.value) * 100}%`,
  height: `${((box.y_max - box.y_min) / height.value) * 100}%`,
});

onMounted(() => dialog.value?.showModal());

// Un clic sur le fond (le <dialog> lui-même, hors de son contenu) ferme la fenêtre ; Échap aussi, nativement.
const onBackdrop = (event: MouseEvent) => {
  if (event.target === dialog.value) emit("close");
};
</script>

<template>
  <dialog ref="dialog" class="entity-dialog" aria-labelledby="entity-dialog-title" @close="emit('close')" @click="onBackdrop">
    <div class="content">
      <header class="header">
        <div>
          <h2 id="entity-dialog-title" class="fr-h6 title">{{ entity.name }}</h2>
          <p class="fr-text--sm muted meta">
            Page {{ pageNumber }} · {{ SOURCES[entity.source] }}
            <template v-if="entity.confidence != null"> · {{ Math.round(entity.confidence * 100) }} %</template>
          </p>
        </div>
        <button type="button" class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" @click="emit('close')">Fermer</button>
      </header>

      <div v-if="region && src" class="crop" :style="{ aspectRatio: String(ratio) }">
        <img
          :src="src"
          :alt="`Zone de la page ${pageNumber} contenant « ${entity.value} »`"
          class="crop-image"
          :style="imageStyle"
          @load="(e) => (natural = { width: (e.target as HTMLImageElement).naturalWidth, height: (e.target as HTMLImageElement).naturalHeight })"
        />
        <span v-for="(box, i) in entity.boxes" :key="i" class="crop-box" :style="boxStyle(box)" aria-hidden="true" />
      </div>
      <p v-else class="fr-text--sm muted">
        {{ region ? "La capture de la page n'est pas disponible." : "Cette valeur n'a pas pu être localisée sur la page." }}
      </p>

      <div class="value-row">
        <p class="value">{{ entity.value }}</p>
        <CopyButton :text="entity.value" />
      </div>
    </div>
  </dialog>
</template>

<style scoped>
.entity-dialog {
  width: min(42rem, calc(100vw - 2rem));
  max-height: calc(100vh - 2rem);
  padding: 0;
  border: 0;
  border-radius: 1rem;
  color: var(--text-default-grey);
  background: var(--background-default-grey);
  box-shadow: 0 1rem 3rem rgb(0 0 0 / 0.25);
}
.entity-dialog::backdrop {
  background: rgb(0 0 0 / 0.45);
}
.content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.25rem 1.5rem 1.5rem;
}
.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}
.title,
.meta {
  margin: 0;
}
.muted {
  color: var(--text-mention-grey);
}
.crop {
  position: relative;
  width: 100%;
  overflow: hidden;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-alt-grey);
}
.crop-image {
  position: absolute;
  max-width: none;
  height: auto;
}
.crop-box {
  position: absolute;
  box-sizing: border-box;
  border: 2px solid var(--border-action-high-blue-france);
  background: color-mix(in srgb, var(--background-action-high-blue-france) 14%, transparent);
  border-radius: 2px;
}
.value-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}
.value {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
  overflow-wrap: anywhere;
  user-select: text;
}
</style>
