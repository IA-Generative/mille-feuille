<script setup lang="ts">
import { ref } from "vue";

import type { ColumnDef, ColumnId } from "@/types/tracking";

// Choix des colonnes visibles et de leur ordre, propres à l'utilisateur.
const props = defineProps<{
  columns: ColumnDef[];
  hidden: ColumnId[];
}>();
const emit = defineEmits<{
  save: [order: ColumnId[], hidden: ColumnId[]];
  reset: [];
  close: [];
}>();

const order = ref<ColumnId[]>(props.columns.map((c) => c.id));
const hiddenSet = ref<Set<ColumnId>>(new Set(props.hidden));
const labelOf = (id: ColumnId) => props.columns.find((c) => c.id === id)?.label ?? id;
const definitionOf = (id: ColumnId) => props.columns.find((c) => c.id === id)?.definition ?? "";

function move(index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= order.value.length) return;
  const next = [...order.value];
  [next[index], next[target]] = [next[target], next[index]];
  order.value = next;
}

function toggle(id: ColumnId, visible: boolean) {
  const next = new Set(hiddenSet.value);
  if (visible) next.delete(id);
  else next.add(id);
  hiddenSet.value = next;
}

const visibleCount = () => order.value.filter((id) => !hiddenSet.value.has(id)).length;

const actions = () => [
  { label: "Enregistrer", disabled: visibleCount() === 0, onClick: () => emit("save", order.value, [...hiddenSet.value]) },
  { label: "Annuler", secondary: true, onClick: () => emit("close") },
  { label: "Rétablir par défaut", tertiary: true, onClick: () => emit("reset") },
];
</script>

<template>
  <DsfrModal :opened="true" title="Colonnes du tableau" icon="ri-layout-column-line" :actions="actions()" @close="emit('close')">
    <p class="cm__hint">Cochez les colonnes à afficher et ordonnez-les avec les flèches. Ce choix est personnel.</p>
    <ul class="cm__list">
      <li v-for="(id, i) in order" :key="id" class="cm__row">
        <label class="cm__label">
          <input type="checkbox" :checked="!hiddenSet.has(id)" @change="toggle(id, ($event.target as HTMLInputElement).checked)" />
          <span class="cm__text">
            {{ labelOf(id) }}
            <span v-if="definitionOf(id)" class="cm__def">{{ definitionOf(id) }}</span>
          </span>
        </label>
        <span class="cm__move">
          <button type="button" class="cm__btn" :disabled="i === 0" :aria-label="`Monter ${labelOf(id)}`" @click="move(i, -1)">
            <VIcon name="ri-arrow-up-s-line" />
          </button>
          <button type="button" class="cm__btn" :disabled="i === order.length - 1" :aria-label="`Descendre ${labelOf(id)}`" @click="move(i, 1)">
            <VIcon name="ri-arrow-down-s-line" />
          </button>
        </span>
      </li>
    </ul>
    <DsfrAlert v-if="visibleCount() === 0" alert type="error" small description="Gardez au moins une colonne visible." class="fr-mt-2w" />
  </DsfrModal>
</template>

<style scoped>
.cm__hint {
  margin: 0 0 0.75rem;
  color: var(--text-mention-grey);
  font-size: 0.875rem;
}

.cm__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.cm__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.375rem 0.25rem;
  border-bottom: 1px solid var(--border-default-grey);
}

.cm__label {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  cursor: pointer;
}

.cm__text {
  display: flex;
  flex-direction: column;
}

.cm__def {
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.cm__btn {
  padding: 0.125rem;
  border: none;
  background: none;
  color: var(--text-default-grey);
  font-size: 1.125rem;
  cursor: pointer;
}

.cm__btn:disabled {
  opacity: 0.3;
  cursor: default;
}
</style>
