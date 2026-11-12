<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import BulkAccessModal from "@/components/access/BulkAccessModal.vue";
import BulkAssignBar from "@/components/tracking/BulkAssignBar.vue";
import ColumnsModal from "@/components/tracking/ColumnsModal.vue";
import CustomFieldsModal from "@/components/tracking/CustomFieldsModal.vue";
import TrackingFiltersPanel from "@/components/tracking/TrackingFilters.vue";
import TrackingTable from "@/components/tracking/TrackingTable.vue";
import TrackingViewsBar from "@/components/tracking/TrackingViewsBar.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { useAuth } from "@/composables/useAuth";
import { useDossierAccess } from "@/composables/useDossierAccess";
import { EXPORT_LIMIT, useTrackingApi } from "@/composables/useTrackingApi";
import { BUILT_IN_VIEWS, useTrackingPrefs } from "@/composables/useTrackingPrefs";
import type { DossierAccess } from "@/types/access";
import {
  emptyFilters,
  type Assignee,
  type ColumnId,
  type CustomValue,
  type TrackingFilters,
  type TrackingListRow,
  type TrackingSort,
} from "@/types/tracking";
import { userMessage } from "@/utils/api";
import { downloadCsv, toCsv } from "@/utils/csv";
import { dueLabel, formatDueDate } from "@/utils/due";
import { formatValue } from "@/utils/trackingFields";

// Tableau de suivi des dossiers, utilisé à deux niveaux :
//  - onglet « Suivi » d'une analyse (`analyseId` fourni) : ses dossiers, ses
//    statuts, ses colonnes personnalisées ;
//  - vue transversale (#186, `analyseId` absent) : les dossiers de toutes les
//    analyses accessibles, avec colonne et filtre « Analyse ».
// La liste, les filtres, le tri, la pagination, l'affectation, les colonnes personnalisées (définitions et valeurs) et
// l'accès par groupe passent par l'API (useTrackingApi, useAnalyses, useDossierAccess).

const props = defineProps<{ analyseId?: string }>();

const route = useRoute();
const { isAdmin } = useAuth();
const transversal = computed(() => !props.analyseId);

const { query, queryAll, assign, setValue, fetchAssignees } = useTrackingApi();
const { saveAccessInBulk } = useDossierAccess();
const { list: analyses, fetchList: fetchAnalyses, getById, fetchAnalyse } = useAnalyses();

const assignees = ref<Assignee[]>([]);
const assigneeName = (id: string | null) => assignees.value.find((a) => a.id === id)?.name ?? "";

/** Statuts proposés au filtre : ceux de l'analyse, ou tous (pour nommer un statut venu d'un lien) en transversal. */
const statuses = computed(() =>
  (singleAnalyseId.value ? analyses.value.filter((a) => a.id === singleAnalyseId.value) : analyses.value).flatMap((a) =>
    [...a.statuses].sort((x, y) => x.position - y.position).map((s) => ({ id: s.id, label: s.name })),
  ),
);

const PAGE_SIZE = 10;

/** Vue ouverte par défaut : « Mes dossiers » en transversal, « Tous » dans une analyse. */
const defaultViewId = transversal.value ? "mine" : "all";
const activeViewId = ref(defaultViewId);
const filters = ref<TrackingFilters>(emptyFilters());
const sort = ref<TrackingSort>({ key: "due", dir: "asc" });
const page = ref(1);

/** Dans une analyse le périmètre est imposé ; en transversal il vient des filtres. */
const effectiveFilters = computed<TrackingFilters>(() => {
  const scoped = props.analyseId ? { ...filters.value, analyseIds: [props.analyseId] } : filters.value;
  // Les colonnes personnalisées dépendent de l'analyse : le serveur n'accepte leurs filtres que pour une seule.
  return singleAnalyseId.value ? scoped : { ...scoped, fieldFilters: {} };
});

/** Colonnes personnalisées : celles de l'analyse, ou celles de l'unique analyse filtrée en transversal. */
const singleAnalyseId = computed(() =>
  props.analyseId ?? (filters.value.analyseIds.length === 1 ? filters.value.analyseIds[0] : undefined),
);
const fields = computed(() => (singleAnalyseId.value ? (getById(singleAnalyseId.value)?.customFields ?? []) : []));
const fieldsAreHidden = computed(() => transversal.value && !singleAnalyseId.value);
// Les définitions des colonnes viennent de l'analyse : on les charge (ou les rafraîchit) dès qu'une seule est concernée.
watch(singleAnalyseId, (id) => id && fetchAnalyse(id), { immediate: true });
// Sans analyse unique, plus de colonne personnalisée : un tri sur l'une d'elles n'a plus de sens.
watch(singleAnalyseId, (id) => {
  if (!id && sort.value.key.startsWith("field:")) sort.value = { key: "due", dir: "asc" };
});

const prefs = useTrackingPrefs(props.analyseId ?? "all", fields);

const rows = ref<TrackingListRow[]>([]);
const total = ref(0);
const loading = ref(false);
const selected = ref<string[]>([]);

const filtersOpen = ref(false);
const columnsOpen = ref(false);
const fieldsOpen = ref(false);
const bulkAccessOpen = ref(false);
const notice = ref("");
const loadError = ref("");

const activeView = computed(() => prefs.views.value.find((v) => v.id === activeViewId.value) ?? BUILT_IN_VIEWS[0]);
const modified = computed(
  () =>
    JSON.stringify(filters.value) !== JSON.stringify(activeView.value.filters) ||
    JSON.stringify(sort.value) !== JSON.stringify(activeView.value.sort),
);

// DsfrPagination travaille avec un index de page commençant à 0.
const pageIndex = computed({
  get: () => page.value - 1,
  set: (index: number) => (page.value = index + 1),
});

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)));
const pages = computed(() => Array.from({ length: pageCount.value }, (_, i) => ({ label: String(i + 1), title: `Page ${i + 1}` })));

let requestSeq = 0;
async function load() {
  const seq = ++requestSeq;
  loading.value = true;
  try {
    const result = await query(effectiveFilters.value, sort.value, page.value, PAGE_SIZE);
    if (seq !== requestSeq) return; // une requête plus récente est partie
    rows.value = result.rows;
    total.value = result.total;
    loadError.value = "";
  } catch (e) {
    if (seq !== requestSeq) return;
    loadError.value = userMessage(e, "Le chargement a échoué.");
  } finally {
    if (seq === requestSeq) loading.value = false;
  }
}

watch([filters, sort, page], load, { deep: true });
// Un changement de filtre ou de tri ramène à la première page.
watch([filters, sort], () => (page.value = 1), { deep: true });
// Une colonne personnalisée disparaît quand le périmètre n'est plus une seule analyse.
watch(singleAnalyseId, () => (selected.value = []));

function applyView(id: string) {
  const view = prefs.views.value.find((v) => v.id === id);
  if (!view) return;
  activeViewId.value = id;
  filters.value = JSON.parse(JSON.stringify(view.filters));
  sort.value = { ...view.sort };
  selected.value = [];
}

onMounted(() => {
  fetchAnalyses(1, 100);
  fetchAssignees().then((list) => (assignees.value = list));
  applyView(defaultViewId);
  // Liens profonds (ex. depuis le tableau de bord) : ?status=…&due=…&assignee=me&analyse=a,b
  const q = route.query;
  const fromUrl: Partial<TrackingFilters> = {};
  if (typeof q.status === "string") fromUrl.statusId = q.status;
  if (typeof q.due === "string") fromUrl.due = q.due;
  if (typeof q.assignee === "string") fromUrl.assignee = q.assignee;
  if (typeof q.analyse === "string" && transversal.value) fromUrl.analyseIds = q.analyse.split(",").filter(Boolean);
  if (Object.keys(fromUrl).length) filters.value = { ...emptyFilters(), ...fromUrl };
  load();
});

function resetFilters() {
  filters.value = emptyFilters();
}

function saveView(name: string) {
  const view = prefs.saveView(name, filters.value, sort.value);
  activeViewId.value = view.id;
  announce(`Vue « ${view.name} » enregistrée.`);
}

function deleteView(id: string) {
  prefs.deleteView(id);
  if (activeViewId.value === id) applyView(defaultViewId);
}

let noticeTimer: ReturnType<typeof setTimeout> | undefined;
function announce(message: string) {
  notice.value = message;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => (notice.value = ""), 5000);
}

/** Définit l'accès de la sélection (administrateurs) en une transaction ; le serveur désaffecte qui perd l'accès. */
async function onBulkAccess(next: DossierAccess) {
  const count = selected.value.length;
  try {
    const result = await saveAccessInBulk(selected.value, next);
    announce(
      `Accès défini pour ${count} dossier${count > 1 ? "s" : ""}${result.unassigned ? ` ; ${result.unassigned} affectation${result.unassigned > 1 ? "s" : ""} annulée${result.unassigned > 1 ? "s" : ""}` : ""}. Tracé dans l'historique de chaque dossier.`,
    );
    selected.value = [];
    bulkAccessOpen.value = false;
  } catch (e) {
    bulkAccessOpen.value = false;
    announce(userMessage(e, "Le changement d'accès a échoué."));
  }
  load();
}

async function onAssign(ids: string[], assigneeId: string | null) {
  try {
    const result = await assign(ids, assigneeId);
    const many = ids.length > 1;
    announce(
      result.updated === 0
        ? "Aucun changement : l'affectation était déjà celle-ci."
        : `${result.updated} dossier${result.updated > 1 ? "s" : ""} ${assigneeId ? `affecté${result.updated > 1 ? "s" : ""} à ${assigneeName(assigneeId)}` : `désaffecté${result.updated > 1 ? "s" : ""}`}. Tracé dans l'historique.`,
    );
    if (many || result.updated) selected.value = [];
  } catch (e) {
    announce(userMessage(e, "L'affectation a échoué."));
  }
  load();
}

function onFieldsSaved(message: string) {
  announce(message);
  load();
}

/** Enregistre une valeur de colonne : le serveur la valide selon le type et renvoie le message à afficher en cas d'erreur. */
async function onSetValue(rowId: string, fieldId: string, value: CustomValue, done: (error: string | null) => void) {
  try {
    await setValue(rowId, fieldId, value);
  } catch (e) {
    done(userMessage(e, "L'enregistrement a échoué."));
    return;
  }
  done(null);
  announce("Valeur enregistrée. Tracée dans l'historique du dossier.");
  load();
}

function onColumnsSaved(order: ColumnId[], hidden: ColumnId[]) {
  prefs.setColumns(order, hidden);
  columnsOpen.value = false;
}

function onColumnsReset() {
  prefs.resetColumns();
  columnsOpen.value = false;
}

/** Export CSV de la vue courante (filtres et tri appliqués, colonnes visibles). */
async function exportCsv() {
  const cols = prefs.visibleColumns.value;
  let result;
  try {
    result = await queryAll(effectiveFilters.value, sort.value);
  } catch (e) {
    announce(userMessage(e, "L'export a échoué."));
    return;
  }
  const cell = (r: TrackingListRow, id: ColumnId): string => {
    switch (id) {
      case "reference":
        return r.reference;
      case "name":
        return r.name;
      case "analyse":
        return r.analyse.name;
      case "status":
        return r.status?.name ?? "";
      case "assignee":
        return r.assignee?.name ?? "";
      case "due":
        return r.dueAt && r.due ? `${formatDueDate(r.dueAt)} (${dueLabel(r.due)})` : "";
      case "createdAt":
        return new Date(r.createdAt).toLocaleDateString("fr-FR");
      case "lastActivityAt":
        return new Date(r.lastActivityAt).toLocaleDateString("fr-FR");
      default: {
        const f = fields.value.find((x) => `field:${x.id}` === id);
        return f ? formatValue(f, r.values[f.id]).replace("—", "") : "";
      }
    }
  };
  downloadCsv(
    `suivi-dossiers-${new Date().toISOString().slice(0, 10)}.csv`,
    toCsv(cols.map((c) => c.label), result.rows.map((r) => cols.map((c) => cell(r, c.id)))),
  );
  const n = result.rows.length;
  announce(
    result.total > n
      ? `${n} lignes exportées sur ${result.total} : l'export est limité à ${EXPORT_LIMIT} lignes, affinez les filtres.`
      : `${n} ligne${n > 1 ? "s" : ""} exportée${n > 1 ? "s" : ""}.`,
  );
}
</script>

<template>
  <div class="track">
    <div class="track__top">
      <TrackingViewsBar
        :views="prefs.views.value"
        :active-id="activeViewId"
        :modified="modified"
        @select="applyView"
        @save="saveView"
        @delete="deleteView"
      />

      <div class="track__tools">
        <button type="button" class="track__tool" :aria-expanded="filtersOpen" @click="filtersOpen = !filtersOpen">
          <VIcon name="ri-filter-3-line" /> Filtres
        </button>
        <details class="track__more">
          <summary class="track__tool"><VIcon name="ri-more-2-fill" /> Options</summary>
          <ul class="track__menu">
            <li><button type="button" class="track__menu-item" @click="columnsOpen = true"><VIcon name="ri-layout-column-line" /> Colonnes</button></li>
            <li v-if="isAdmin && analyseId">
              <button type="button" class="track__menu-item" @click="fieldsOpen = true"><VIcon name="ri-table-line" /> Champs personnalisés</button>
            </li>
            <li><button type="button" class="track__menu-item" @click="exportCsv"><VIcon name="ri-download-2-line" /> Exporter en CSV</button></li>
          </ul>
        </details>
      </div>
    </div>

    <TrackingFiltersPanel
      v-if="filtersOpen"
      v-model="filters"
      :statuses="statuses"
      :assignees="assignees"
      :analyses="analyses"
      :fields="fields"
      :transversal="transversal"
      show-access
      @reset="resetFilters"
    />

    <BulkAssignBar
      v-if="selected.length"
      :count="selected.length"
      :assignees="assignees"
      :can-set-access="isAdmin"
      @assign="(id) => onAssign(selected, id)"
      @set-access="bulkAccessOpen = true"
      @clear="selected = []"
    />

    <DsfrAlert v-if="loadError" alert type="error" small class="fr-mb-2w">
      <p>{{ loadError }} <button type="button" class="track__tool" @click="load">Réessayer</button></p>
    </DsfrAlert>
    <p class="track__count" aria-live="polite">{{ total }} dossier{{ total > 1 ? "s" : "" }}</p>
    <p v-if="fieldsAreHidden" class="track__hint">
      Les colonnes personnalisées dépendent de l'analyse : filtrez sur une seule analyse pour les afficher.
    </p>

    <TrackingTable
      v-model:sort="sort"
      v-model:selected="selected"
      :rows="rows"
      :columns="prefs.visibleColumns.value"
      :fields="fields"
      :assignees="assignees"
      :loading="loading"
      :can-assign="() => true"
      @assign="(id, assigneeId) => onAssign([id], assigneeId)"
      @set-value="onSetValue"
    />

    <DsfrPagination v-if="pageCount > 1" v-model:current-page="pageIndex" :pages="pages" class="track__pagination" />

    <p class="track__notice" role="status">{{ notice }}</p>

    <BulkAccessModal v-if="bulkAccessOpen" :count="selected.length" @apply="onBulkAccess" @close="bulkAccessOpen = false" />

    <ColumnsModal
      v-if="columnsOpen"
      :columns="prefs.allColumns.value"
      :hidden="prefs.hiddenColumns.value"
      @save="onColumnsSaved"
      @reset="onColumnsReset"
      @close="columnsOpen = false"
    />
    <CustomFieldsModal v-if="fieldsOpen && analyseId" :analyse-id="analyseId" @close="fieldsOpen = false" @saved="onFieldsSaved" />
  </div>
</template>

<style scoped>
.track {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.track__top {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.track__tools {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
}

.track__tool {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0;
  border: none;
  background: none;
  color: var(--text-action-high-blue-france);
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}

.track__more {
  position: relative;
}

.track__more > summary {
  list-style: none;
  cursor: pointer;
}

.track__more > summary::-webkit-details-marker {
  display: none;
}

.track__menu {
  position: absolute;
  top: 1.75rem;
  left: 0;
  z-index: 10;
  min-width: 14rem;
  margin: 0;
  padding: 0.25rem;
  list-style: none;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-default-grey);
  box-shadow: 0 4px 12px rgb(0 0 0 / 15%);
}

.track__menu-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.5rem 0.625rem;
  border: none;
  border-radius: 0.375rem;
  background: none;
  color: var(--text-default-grey);
  font: inherit;
  font-size: 0.875rem;
  text-align: left;
  cursor: pointer;
}

.track__menu-item:hover {
  background: var(--background-alt-grey-hover);
}

.track__hint {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.track__count {
  margin: 0;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}

.track__pagination {
  margin-top: 0.5rem;
}

.track__notice {
  min-height: 1.25rem;
  margin: 0;
  font-size: 0.875rem;
  color: var(--text-default-success);
}
</style>
