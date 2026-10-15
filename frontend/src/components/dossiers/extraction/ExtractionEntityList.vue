<script setup lang="ts">
import type { ExtractedEntity } from "@/types/dossierExtraction";

defineProps<{ entities: ExtractedEntity[]; active: number | null; filtering: boolean }>();
const emit = defineEmits<{ activate: [index: number | null] }>();

const SOURCES: Record<string, string> = { textual: "Texte", visual: "Visuel", gliner: "GLiNER" };
const percent = (c?: number) => (c === undefined ? "" : `${Math.round(c * 100)} %`);
</script>

<template>
  <ul class="extraction-entities">
    <li
      v-for="(entity, i) in entities"
      :key="entity.id"
      class="extraction-entities__item"
      :class="{ 'extraction-entities__item--active': active === i }"
      tabindex="0"
      @mouseenter="emit('activate', i)"
      @mouseleave="emit('activate', null)"
      @focus="emit('activate', i)"
      @blur="emit('activate', null)"
    >
      <span class="extraction-entities__number" aria-hidden="true">{{ i + 1 }}</span>
      <div class="extraction-entities__body">
        <span class="fr-text--sm extraction-entities__muted">{{ entity.name }}</span>
        <strong>{{ entity.value }}</strong>
        <small class="extraction-entities__muted">
          {{ percent(entity.confidence) }} · {{ SOURCES[entity.source] ?? entity.source }}
          <template v-if="!entity.boxes.length"> · non localisée</template>
        </small>
      </div>
    </li>
    <li v-if="!entities.length" class="fr-text--sm extraction-entities__muted extraction-entities__empty">
      {{ filtering ? "Aucune entité de cette page ne correspond." : "Aucune entité sur cette page." }}
    </li>
  </ul>
</template>

<style scoped>
.extraction-entities {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.extraction-entities__item {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  padding: 0.6rem 0.9rem;
  border-radius: 0.75rem;
  background: var(--background-alt-grey);
  outline-offset: 2px;
}

.extraction-entities__item--active,
.extraction-entities__item:focus-visible {
  outline: 2px solid var(--border-action-high-blue-france);
}

.extraction-entities__number {
  flex: 0 0 auto;
  min-width: 1.5rem;
  height: 1.5rem;
  line-height: 1.5rem;
  text-align: center;
  font-size: 0.8rem;
  border-radius: 50%;
  color: #fff;
  background: var(--background-action-high-blue-france);
}

.extraction-entities__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow-wrap: anywhere;
}

.extraction-entities__muted {
  color: var(--text-mention-grey);
}

.extraction-entities__empty {
  padding: 1rem 0;
}
</style>
