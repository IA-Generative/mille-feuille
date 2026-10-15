<script setup lang="ts">
import CopyButton from "@/components/CopyButton.vue";
import type { EntityResult } from "@/types";

defineProps<{ entities: EntityResult[]; active: number | null; filtering: boolean }>();
const emit = defineEmits<{ activate: [index: number | null]; open: [index: number] }>();

const SOURCES: Record<string, string> = { textual: "Texte", visual: "Visuel", gliner: "GLiNER" };
const percent = (c: number | null) => (c == null ? "" : `${Math.round(c * 100)} %`);
</script>

<template>
  <ul class="entities">
    <li
      v-for="(entity, i) in entities"
      :key="entity.prediction_id ?? i"
      class="entity"
      :class="{ active: active === i }"
      @mouseenter="emit('activate', i)"
      @mouseleave="emit('activate', null)"
      @focusin="emit('activate', i)"
      @focusout="emit('activate', null)"
    >
      <button type="button" class="open" :aria-label="`Voir ${entity.name} : ${entity.value}`" @click="emit('open', i)">
        <span class="number" aria-hidden="true">{{ i + 1 }}</span>
        <span class="body">
          <span class="fr-text--sm muted">{{ entity.name }}</span>
          <strong>{{ entity.value }}</strong>
          <small class="muted">
            {{ percent(entity.confidence) }} · {{ SOURCES[entity.source] }}
            <template v-if="!entity.boxes.length"> · non localisée</template>
          </small>
        </span>
      </button>
      <CopyButton :text="entity.value" />
    </li>
    <li v-if="!entities.length" class="empty fr-text--sm muted">
      {{ filtering ? "Aucune entité de cette page ne correspond." : "Aucune entité sur cette page." }}
    </li>
  </ul>
</template>

<style scoped>
.entities {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.entity {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  padding: 0.6rem 0.5rem 0.6rem 0.9rem;
  border-radius: 0.75rem;
  background: var(--background-alt-grey);
  outline-offset: 2px;
}
.entity.active,
.entity:focus-within {
  outline: 2px solid var(--border-action-high-blue-france);
}
.open {
  flex: 1;
  min-width: 0;
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.number {
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
.body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow-wrap: anywhere;
}
.muted {
  color: var(--text-mention-grey);
}
.empty {
  padding: 1rem 0;
}
</style>
