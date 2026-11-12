<script setup lang="ts">
import { computed, ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import ErrorList from "@/components/ErrorList.vue";
import WorkflowStatusBadge from "@/components/statuses/WorkflowStatusBadge.vue";
import type { StatusDraft, Version, WorkflowStatus } from "@/types/analyse";

// Configuration des statuts de dossier d'une analyse (issue #170) : nom,
// couleur, ordre, statut initial (un seul) et statuts finaux. Versionné avec
// historique et restauration, comme les autres champs d'une analyse.
const props = defineProps<{ statuses: WorkflowStatus[]; versions: Version<WorkflowStatus[]>[]; saving?: boolean }>();
const emit = defineEmits<{ save: [drafts: StatusDraft[]]; restore: [versionId: string] }>();

interface Row extends StatusDraft {
  /** Clé stable pour la liste (le statut n'a pas encore d'id tant qu'il n'est pas enregistré). */
  key: string;
}

const toRows = (statuses: WorkflowStatus[]): Row[] =>
  [...statuses]
    .sort((a, b) => a.position - b.position)
    .map(({ id, name, color, isInitial, isFinal }) => ({ key: id, id, name, color, isInitial, isFinal }));

const rows = ref<Row[]>(toRows(props.statuses));
let newCount = 0;

watch(
  () => props.statuses,
  (statuses) => (rows.value = toRows(statuses)),
);

const signature = (list: { id: string | null; name: string; color: string; isInitial: boolean; isFinal: boolean }[]) =>
  JSON.stringify(list.map(({ id, name, color, isInitial, isFinal }) => [id, name.trim(), color.toLowerCase(), isInitial, isFinal]));

const isDirty = computed(() => signature(rows.value) !== signature(toRows(props.statuses)));

const errors = computed(() => {
  const list: string[] = [];
  if (rows.value.length === 0) list.push("Une analyse doit avoir au moins un statut.");
  if (rows.value.some((r) => !r.name.trim())) list.push("Chaque statut doit avoir un nom.");
  const names = rows.value.map((r) => r.name.trim().toLowerCase()).filter(Boolean);
  if (new Set(names).size !== names.length) list.push("Deux statuts ne peuvent pas porter le même nom.");
  if (rows.value.length > 0 && rows.value.filter((r) => r.isInitial).length !== 1) {
    list.push("Choisissez exactement un statut initial : celui que reçoit un dossier créé.");
  }
  return list;
});

function addStatus() {
  rows.value.push({ key: `new-${++newCount}`, id: null, name: "", color: "#6a6af4", isInitial: false, isFinal: false });
}

function removeStatus(key: string) {
  rows.value = rows.value.filter((r) => r.key !== key);
}

function move(index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= rows.value.length) return;
  const next = [...rows.value];
  [next[index], next[target]] = [next[target], next[index]];
  rows.value = next;
}

/** Un seul statut initial ; un statut initial ne peut pas être final. */
function setInitial(key: string) {
  for (const row of rows.value) {
    row.isInitial = row.key === key;
    if (row.isInitial) row.isFinal = false;
  }
}

function save() {
  if (errors.value.length || !isDirty.value) return;
  emit(
    "save",
    rows.value.map(({ id, name, color, isInitial, isFinal }) => ({ id, name: name.trim(), color, isInitial, isFinal })),
  );
}

function formatVersion(statuses: WorkflowStatus[]) {
  return statuses.length
    ? [...statuses]
        .sort((a, b) => a.position - b.position)
        .map((s) => `${s.name}${s.isInitial ? " (initial)" : ""}${s.isFinal ? " (final)" : ""}`)
        .join(" → ")
    : "(aucun statut)";
}
</script>

<template>
  <div class="se">
    <h4 class="fr-h6 se__title">Statuts de dossier</h4>
    <p class="fr-text--sm se__intro">
      Les statuts disent où en est un dossier dans son traitement. Le <strong>statut initial</strong> est celui que reçoit
      un dossier créé ; un <strong>statut final</strong> clôt le dossier (une date de clôture est alors enregistrée).
    </p>

    <ul class="se__list">
      <li v-for="(row, index) in rows" :key="row.key" class="se__row">
        <div class="se__order">
          <button type="button" class="se__icon-btn" :disabled="index === 0" :aria-label="`Monter ${row.name || 'le statut'}`" @click="move(index, -1)">
            <VIcon name="ri-arrow-up-s-line" />
          </button>
          <button type="button" class="se__icon-btn" :disabled="index === rows.length - 1" :aria-label="`Descendre ${row.name || 'le statut'}`" @click="move(index, 1)">
            <VIcon name="ri-arrow-down-s-line" />
          </button>
        </div>

        <label class="se__color">
          <span class="fr-sr-only">Couleur de {{ row.name || "ce statut" }}</span>
          <input v-model="row.color" type="color" />
        </label>

        <div class="se__name"><DsfrInput v-model="row.name" label="Nom du statut" label-visible /></div>

        <label class="se__check">
          <input type="radio" name="initial-status" :checked="row.isInitial" @change="setInitial(row.key)" />
          Initial
        </label>
        <label class="se__check">
          <input v-model="row.isFinal" type="checkbox" :disabled="row.isInitial" />
          Final
        </label>

        <WorkflowStatusBadge v-if="row.name.trim()" :status="row" class="se__preview" />

        <button type="button" class="se__icon-btn se__delete" :aria-label="`Supprimer ${row.name || 'le statut'}`" @click="removeStatus(row.key)">
          <VIcon name="ri-delete-bin-line" />
        </button>
      </li>
    </ul>

    <ErrorList :errors="errors" class="fr-my-2w" />

    <div class="se__actions">
      <DsfrButton label="Ajouter un statut" tertiary icon="ri-add-line" size="sm" @click="addStatus" />
      <DsfrButton label="Enregistrer" size="sm" :disabled="!isDirty || errors.length > 0 || saving" @click="save" />
    </div>

    <VersionHistory :versions="versions" :format-content="formatVersion" @restore="emit('restore', $event)" />
  </div>
</template>

<style scoped>
.se {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.se__title,
.se__intro {
  margin: 0;
}

.se__list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.se__row {
  display: grid;
  grid-template-columns: auto auto minmax(10rem, 1fr) auto auto auto auto;
  align-items: end;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-default-grey);
}

.se__order {
  display: flex;
  flex-direction: column;
}

.se__icon-btn {
  display: flex;
  padding: 0.125rem;
  border: none;
  background: none;
  color: var(--text-default-grey);
  font-size: 1.125rem;
  cursor: pointer;
}

.se__icon-btn:disabled {
  opacity: 0.3;
  cursor: default;
}

.se__color {
  padding-bottom: 0.25rem;
}

.se__color input {
  width: 2.5rem;
  height: 2.5rem;
  padding: 0;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.375rem;
  background: none;
  cursor: pointer;
}

.se__name {
  min-width: 0;
}

.se__name :deep(.fr-input-group) {
  margin: 0;
}

@media (max-width: 48em) {
  .se__row {
    grid-template-columns: auto auto 1fr;
  }

  .se__name {
    grid-column: 1 / -1;
    order: 5;
  }
}

.se__check {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding-bottom: 0.5rem;
}

.se__preview {
  margin-bottom: 0.5rem;
}

.se__delete {
  margin-bottom: 0.5rem;
  color: var(--text-default-error);
}

.se__actions {
  display: flex;
  gap: 0.75rem;
}
</style>
