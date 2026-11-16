<script setup lang="ts">
import { computed } from "vue";
import { RouterLink } from "vue-router";

import AccessBadge from "@/components/access/AccessBadge.vue";
import InfoTip from "@/components/InfoTip.vue";
import CellEditor from "@/components/tracking/CellEditor.vue";
import DossierDueBadge from "@/components/dossiers/DossierDueBadge.vue";
import WorkflowStatusBadge from "@/components/statuses/WorkflowStatusBadge.vue";
import type { Assignee, ColumnDef, CustomField, CustomValue, TrackingListRow, TrackingSort } from "@/types/tracking";

// Tableau de suivi : tri par en-tête, sélection de lignes, affectation
// directe dans la ligne, édition en cellule des champs personnalisés.
const props = defineProps<{
  rows: TrackingListRow[];
  columns: ColumnDef[];
  fields: CustomField[];
  assignees: Assignee[];
  sort: TrackingSort;
  selected: string[];
  loading: boolean;
  /** Une personne peut-elle être affectée à ce dossier ? (elle doit y avoir accès, #177) */
  canAssign: (rowId: string, assigneeId: string) => boolean;
}>();

const emit = defineEmits<{
  "update:sort": [sort: TrackingSort];
  "update:selected": [ids: string[]];
  assign: [rowId: string, assigneeId: string | null];
  "set-value": [rowId: string, fieldId: string, value: CustomValue, done: (error: string | null) => void];
}>();

const allSelected = computed(() => props.rows.length > 0 && props.rows.every((r) => props.selected.includes(r.id)));

function toggleAll(checked: boolean) {
  const pageIds = props.rows.map((r) => r.id);
  emit(
    "update:selected",
    checked ? [...new Set([...props.selected, ...pageIds])] : props.selected.filter((id) => !pageIds.includes(id)),
  );
}

function toggleRow(id: string, checked: boolean) {
  emit("update:selected", checked ? [...props.selected, id] : props.selected.filter((x) => x !== id));
}

function sortBy(id: ColumnDef["id"]) {
  emit("update:sort", { key: id, dir: props.sort.key === id && props.sort.dir === "asc" ? "desc" : "asc" });
}

const ariaSort = (id: ColumnDef["id"]) =>
  props.sort.key === id ? (props.sort.dir === "asc" ? "ascending" : "descending") : "none";

const fieldOf = (id: ColumnDef["id"]) => props.fields.find((f) => `field:${f.id}` === id);

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
}
</script>

<template>
  <div class="tt" :aria-busy="loading">
    <table class="tt__table">
      <caption class="fr-sr-only">Suivi des dossiers de l'analyse</caption>
      <thead>
        <tr>
          <th scope="col" class="tt__check">
            <input type="checkbox" :checked="allSelected" aria-label="Sélectionner toute la page" @change="toggleAll(($event.target as HTMLInputElement).checked)" />
          </th>
          <th v-for="c in columns" :key="c.id" scope="col" :aria-sort="c.sortable ? ariaSort(c.id) : undefined">
            <span class="tt__th">
              <button v-if="c.sortable" type="button" class="tt__sort" @click="sortBy(c.id)">
                {{ c.label }}
                <VIcon
                  :name="sort.key === c.id ? (sort.dir === 'asc' ? 'ri-arrow-up-s-line' : 'ri-arrow-down-s-line') : 'ri-expand-up-down-line'"
                  :class="{ 'tt__sort-idle': sort.key !== c.id }"
                />
              </button>
              <template v-else>{{ c.label }}</template>
              <span v-if="c.definition" class="tt__help">
                <InfoTip :content="c.definition" :label="`Aide sur la colonne ${c.label}`" />
              </span>
            </span>
          </th>
        </tr>
      </thead>
      <tbody :class="{ 'tt__body--loading': loading }">
        <tr v-for="r in rows" :key="r.id" :class="{ 'tt__row--selected': selected.includes(r.id) }">
          <td class="tt__check">
            <input type="checkbox" :checked="selected.includes(r.id)" :aria-label="`Sélectionner ${r.reference}`" @change="toggleRow(r.id, ($event.target as HTMLInputElement).checked)" />
          </td>
          <td v-for="c in columns" :key="c.id">
            <template v-if="c.id === 'reference'">
              <RouterLink :to="`/dossiers/${r.id}`" class="tt__ref">{{ r.reference }}</RouterLink>
              <AccessBadge :visibility="r.visibility" class="fr-ml-1w" />
            </template>
            <template v-else-if="c.id === 'name'">{{ r.name }}</template>
            <RouterLink v-else-if="c.id === 'analyse'" :to="`/analyses/${r.analyse.id}/suivi`">{{ r.analyse.name }}</RouterLink>
            <WorkflowStatusBadge v-else-if="c.id === 'status' && r.status" :status="r.status" />
            <span v-else-if="c.id === 'status'" class="tt__none">—</span>
            <select
              v-else-if="c.id === 'assignee'"
              class="fr-select tt__assignee"
              :value="r.assignee?.id ?? ''"
              :aria-label="`Affecté à — ${r.reference}`"
              @change="emit('assign', r.id, ($event.target as HTMLSelectElement).value || null)"
            >
              <option value="">Non affecté</option>
              <option v-for="a in assignees.filter((x) => canAssign(r.id, x.id) || x.id === r.assignee?.id)" :key="a.id" :value="a.id">{{ a.name }}</option>
            </select>
            <DossierDueBadge v-else-if="c.id === 'due' && r.due" :due="r.due" compact />
            <span v-else-if="c.id === 'due'" class="tt__none">—</span>
            <template v-else-if="c.id === 'createdAt'">{{ formatDate(r.createdAt) }}</template>
            <template v-else-if="c.id === 'lastActivityAt'">{{ formatDate(r.lastActivityAt) }}</template>
            <CellEditor
              v-else-if="fieldOf(c.id)"
              :field="fieldOf(c.id)!"
              :value="r.values[fieldOf(c.id)!.id]"
              :label="r.reference"
              @save="(value, done) => emit('set-value', r.id, fieldOf(c.id)!.id, value, done)"
            />
          </td>
        </tr>
        <tr v-if="rows.length === 0 && !loading">
          <td :colspan="columns.length + 1" class="tt__empty">Aucun dossier ne correspond à ces critères.</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.tt__none {
  color: var(--text-mention-grey);
}

.tt {
  overflow-x: auto;
  min-height: 12rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
}

.tt__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.tt__table th,
.tt__table td {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--border-default-grey);
  text-align: left;
  vertical-align: middle;
  white-space: nowrap;
}

.tt__table thead th {
  background: var(--background-alt-grey);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--text-mention-grey);
}

.tt__table tbody tr:last-child td {
  border-bottom: none;
}

.tt__table tbody tr:hover {
  background: var(--background-alt-grey-hover);
}

.tt__row--selected {
  background: var(--background-action-low-blue-france);
}

.tt__check {
  width: 2.5rem;
}

.tt__th {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}

/* Les en-têtes sont en majuscules, en gras et sur une ligne : la bulle d'aide doit redevenir un texte normal. */
.tt__help {
  text-transform: none;
  letter-spacing: normal;
  font-weight: 400;
  white-space: normal;
}

.tt__sort {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0;
  border: none;
  background: none;
  color: inherit;
  font: inherit;
  letter-spacing: inherit;
  text-transform: inherit;
  cursor: pointer;
}

.tt__sort-idle {
  opacity: 0.4;
}

.tt__ref {
  font-weight: 600;
}

.tt__assignee {
  min-width: 10rem;
  padding: 0.25rem 2rem 0.25rem 0.5rem;
}

.tt__body--loading {
  opacity: 0.5;
}

.tt__empty {
  padding: 2rem;
  text-align: center;
  color: var(--text-mention-grey);
}
</style>
