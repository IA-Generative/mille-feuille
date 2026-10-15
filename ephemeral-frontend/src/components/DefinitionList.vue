<script setup lang="ts">
import type { EntityType } from "@/types";

interface Row {
  name: string;
  definition: string;
  type?: EntityType;
}

defineProps<{ withType?: boolean; addLabel: string; namePlaceholder: string; definitionPlaceholder?: string }>();
const rows = defineModel<Row[]>({ required: true });

const TYPES: EntityType[] = ["texte", "date", "nombre", "booléen", "identifiant"];
const add = (withType?: boolean) => rows.value.push({ name: "", definition: "", ...(withType ? { type: "texte" } : {}) });
const remove = (index: number) => rows.value.splice(index, 1);
</script>

<template>
  <div class="rows">
    <div v-for="(row, index) in rows" :key="index" class="row">
      <input v-model="row.name" class="fr-input" :placeholder="namePlaceholder" :aria-label="namePlaceholder" />
      <select v-if="withType" v-model="row.type" class="fr-select type" aria-label="Type" title="Type de la valeur attendue">
        <option v-for="type in TYPES" :key="type">{{ type }}</option>
      </select>
      <input v-model="row.definition" class="fr-input grow" :placeholder="definitionPlaceholder ?? 'Définition (aide le modèle)'"
        aria-label="Définition" />
      <button
        type="button"
        class="fr-btn fr-btn--tertiary-no-outline fr-icon-delete-line"
        title="Retirer"
        :disabled="rows.length === 1"
        @click="remove(index)"
      >
        Retirer
      </button>
    </div>
    <button type="button" class="fr-btn fr-btn--tertiary fr-btn--sm fr-icon-add-line fr-btn--icon-left" @click="add(withType)">
      {{ addLabel }}
    </button>
  </div>
</template>

<style scoped>
.rows {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: flex-start;
}
.row {
  display: flex;
  gap: 0.5rem;
  width: 100%;
  flex-wrap: wrap;
}
.row > input:first-child {
  flex: 1 1 10rem;
}
.grow {
  flex: 3 1 14rem;
}
.type {
  flex: 0 0 9rem;
}
</style>
