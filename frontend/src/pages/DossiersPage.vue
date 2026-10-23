<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import AccessBadge from "@/components/access/AccessBadge.vue";
import PagerNav from "@/components/PagerNav.vue";
import DossierDueBadge from "@/components/dossiers/DossierDueBadge.vue";
import CreateDossierModal from "@/components/dossiers/CreateDossierModal.vue";
import WorkflowStatusBadge from "@/components/statuses/WorkflowStatusBadge.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { useDossiers } from "@/composables/useDossiers";
import {
  DOSSIER_STATUS_LABELS,
  SUGGESTION_STATUS_LABELS,
  type Dossier,
  type DossierStatus,
  type SuggestionStatus,
} from "@/types/dossier";

const router = useRouter();
const route = useRoute();
const { list: dossiers, pageCount, fetchList, launch, stop, suggestAnalyse } = useDossiers();
const { list: analyses, fetchList: fetchAnalyses } = useAnalyses();

const isCreateModalOpened = ref(false);

const PAGE_SIZE = 10;
const currentPage = ref(1);

// Filtre par statut de dossier et tri (#170) ; le filtre se lit dans l'URL (?status=<id>) pour que le
// tableau de bord et le suivi puissent y renvoyer.
const statusFilter = ref(typeof route.query.status === "string" ? route.query.status : "");
const dueFilter = ref<"" | "overdue" | "7" | "30" | "none">(
  ["overdue", "7", "30", "none"].includes(String(route.query.due)) ? (String(route.query.due) as "overdue" | "7" | "30" | "none") : "",
);
const sort = ref<"created_at" | "status" | "due">("created_at");

watch(
  [currentPage, statusFilter, dueFilter, sort],
  () =>
    fetchList(currentPage.value, PAGE_SIZE, {
      workflowStatusId: statusFilter.value || undefined,
      due: dueFilter.value || undefined,
      sort: sort.value,
    }),
  { immediate: true },
);
// Un changement de filtre ou de tri ramène à la première page.
watch([statusFilter, dueFilter, sort], () => (currentPage.value = 1));

/** Statuts de toutes les analyses ; le nom de l'analyse les distingue quand il y en a plusieurs. */
const statusOptions = computed(() => [
  { value: "", text: "Tous les statuts" },
  ...analyses.value.flatMap((a) =>
    [...a.statuses]
      .sort((x, y) => x.position - y.position)
      .map((s) => ({ value: s.id, text: analyses.value.length > 1 ? `${a.name} — ${s.name}` : s.name })),
  ),
]);
// La table affiche le nom de l'analyse liée à chaque dossier : la liste
// paginée par défaut (6-20 éléments) ne couvre pas forcément toutes les
// analyses existantes, donc on en charge une fenêtre large dédiée à cette
// page plutôt que de dépendre de ce qu'une autre page a chargé en dernier.
onMounted(() => fetchAnalyses(1, 100));

const statusBadgeType: Record<DossierStatus, "new" | "info" | "success" | "warning" | "error"> = {
  en_attente: "new",
  en_cours: "info",
  terminé: "success",
  arrêté: "warning",
  échec: "error",
};

function analyseName(dossier: Dossier) {
  if (!dossier.analyseId) return "À ranger";
  return analyses.value.find((a) => a.id === dossier.analyseId)?.name ?? "Analyse introuvable";
}

function formatDate(iso?: string) {
  if (!iso) return "-";
  return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function formatTime(iso?: string) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

/** Date la plus pertinente selon le statut : terminé → endedAt, en cours → startedAt, sinon createdAt. */
function relevantDate(dossier: Dossier) {
  if (dossier.endedAt) return dossier.endedAt;
  if (dossier.startedAt) return dossier.startedAt;
  return dossier.createdAt;
}

const suggestionBadgeType: Record<SuggestionStatus, "new" | "info" | "success" | "warning" | "error"> = {
  en_attente: "new",
  en_cours: "info",
  terminé: "success",
  échec: "error",
};

function goToDossier(dossier: Dossier) {
  router.push(`/dossiers/${dossier.id}`);
}

function isUnassigned(dossier: Dossier) {
  return !dossier.analyseId;
}
</script>

<template>
  <div>
    <div class="dossiers-page__header">
      <div>
        <h1 class="fr-h2">Dossiers</h1>
        <p class="fr-text--lead">Dossiers usagers liés à une analyse, et suivi de leur exécution.</p>
      </div>
      <DsfrButton label="Créer un dossier" icon="ri-add-line" @click="isCreateModalOpened = true" />
    </div>

    <div class="dossiers-page__filters">
      <div>
        <label for="dossiers-status-filter" class="dossiers-page__filter-label">Statut</label>
        <select id="dossiers-status-filter" v-model="statusFilter" class="fr-select">
          <option v-for="o in statusOptions" :key="o.value" :value="o.value">{{ o.text }}</option>
        </select>
      </div>
      <div>
        <label for="dossiers-due-filter" class="dossiers-page__filter-label">Échéance</label>
        <select id="dossiers-due-filter" v-model="dueFilter" class="fr-select">
          <option value="">Toutes les échéances</option>
          <option value="overdue">Dépassée</option>
          <option value="7">Dans 7 jours ou moins</option>
          <option value="30">Dans 30 jours ou moins</option>
          <option value="none">Sans échéance</option>
        </select>
      </div>
      <div>
        <label for="dossiers-sort" class="dossiers-page__filter-label">Trier par</label>
        <select id="dossiers-sort" v-model="sort" class="fr-select">
          <option value="created_at">Date (plus récents d'abord)</option>
          <option value="status">Statut</option>
          <option value="due">Échéance (la plus proche d'abord)</option>
        </select>
      </div>
    </div>

    <p v-if="dossiers.length === 0" class="fr-text--sm">
      {{ statusFilter || dueFilter ? "Aucun dossier ne correspond à ces filtres." : "Aucun dossier pour le moment." }}
    </p>

    <div v-else class="fr-table">
      <div class="fr-table__wrapper">
        <div class="fr-table__container">
          <div class="fr-table__content">
            <table class="dossiers-page__table">
              <thead>
                <tr>
                  <th scope="col">Dossier</th>
                  <th scope="col">Analyse</th>
                  <th scope="col">Statut</th>
                  <th scope="col">Échéance</th>
                  <th scope="col">Exécution</th>
                  <th scope="col">Date</th>
                  <th scope="col" class="dossiers-page__actions-col">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="dossier in dossiers"
                  :key="dossier.id"
                  class="dossiers-page__row"
                  @click="goToDossier(dossier)"
                >
                  <td>
                    <RouterLink :to="`/dossiers/${dossier.id}`" class="dossiers-page__name-link" @click.stop>
                      {{ dossier.name }}
                    </RouterLink>
                    <AccessBadge :visibility="dossier.visibility" class="fr-ml-1w" />
                  </td>
                  <td>
                    <div class="dossiers-page__analyse-cell">
                      <span class="dossiers-page__analyse-name">{{ analyseName(dossier) }}</span>
                      <span v-if="!isUnassigned(dossier)" class="fr-text--xs dossiers-page__version">v{{ dossier.analyseVersion }}</span>
                      <DsfrBadge
                        v-if="isUnassigned(dossier)"
                        :label="SUGGESTION_STATUS_LABELS[dossier.suggestionStatus]"
                        :type="suggestionBadgeType[dossier.suggestionStatus]"
                        small
                        class="dossiers-page__suggestion-badge"
                      />
                    </div>
                  </td>
                  <td>
                    <WorkflowStatusBadge v-if="dossier.workflowStatus" :status="dossier.workflowStatus" />
                    <span v-else class="fr-text--xs dossiers-page__no-status">—</span>
                  </td>
                  <td>
                    <DossierDueBadge v-if="dossier.due" :due="dossier.due" compact />
                    <span v-else class="fr-text--xs dossiers-page__no-status">—</span>
                  </td>
                  <td><DsfrBadge :label="DOSSIER_STATUS_LABELS[dossier.status]" :type="statusBadgeType[dossier.status]" small /></td>
                  <td>
                    <div class="dossiers-page__date-cell">
                      <span>{{ formatDate(relevantDate(dossier)) }}</span>
                      <span class="fr-text--xs dossiers-page__time">{{ formatTime(relevantDate(dossier)) }}</span>
                    </div>
                  </td>
                  <td @click.stop>
                    <div class="dossiers-page__actions">
                      <DsfrButton
                        v-if="isUnassigned(dossier)"
                        label="Suggérer"
                        secondary
                        icon="ri-lightbulb-flash-line"
                        size="sm"
                        :disabled="dossier.suggestionStatus === 'en_cours'"
                        @click="suggestAnalyse(dossier.id)"
                      />
                      <DsfrButton
                        v-else-if="dossier.status === 'en_cours'"
                        label="Arrêter"
                        secondary
                        icon="ri-stop-circle-line"
                        size="sm"
                        @click="stop(dossier.id)"
                      />
                      <DsfrButton
                        v-else-if="(dossier.status === 'en_attente' || dossier.status === 'arrêté') && !isUnassigned(dossier)"
                        label="Lancer"
                        icon="ri-play-circle-line"
                        size="sm"
                        @click="launch(dossier.id)"
                      />
                      <DsfrButton
                        v-if="dossier.status === 'échec' && !isUnassigned(dossier)"
                        label="Relancer"
                        secondary
                        icon="ri-refresh-line"
                        size="sm"
                        @click="launch(dossier.id)"
                      />
                      <RouterLink
                        v-if="dossier.status === 'terminé' || dossier.status === 'échec'"
                        :to="`/dossiers/${dossier.id}`"
                        class="fr-btn fr-btn--tertiary fr-btn--sm fr-icon-eye-line"
                        title="Voir le résultat"
                      />
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <PagerNav v-model:page="currentPage" :page-count="pageCount" class="dossiers-page__pagination" />

    <CreateDossierModal v-model:opened="isCreateModalOpened" />
  </div>
</template>

<style scoped>
.dossiers-page__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 1rem;
}

.dossiers-page__filter-label {
  display: block;
  margin-bottom: 0.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
}

.dossiers-page__no-status {
  color: var(--text-mention-grey);
}

.dossiers-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.dossiers-page__table {
  width: 100%;
}

.dossiers-page__row {
  cursor: pointer;
  transition: background-color 0.1s ease;
}

.dossiers-page__row:hover {
  background-color: var(--background-alt-grey);
}

.dossiers-page__table :deep(td:first-child) {
  max-width: 16rem;
  white-space: normal;
}

.dossiers-page__name-link {
  font-weight: 500;
}

.dossiers-page__table :deep(td),
.dossiers-page__table :deep(th) {
  padding: 0.75rem 0.5rem;
  vertical-align: middle;
}

.dossiers-page__analyse-cell {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.dossiers-page__analyse-name {
  font-weight: 500;
}

.dossiers-page__version {
  color: var(--text-mention-grey);
}

.dossiers-page__suggestion-badge {
  margin-top: 0.25rem;
}

.dossiers-page__date-cell {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.dossiers-page__time {
  color: var(--text-mention-grey);
}

.dossiers-page__actions-col {
  white-space: nowrap;
}

.dossiers-page__actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  white-space: nowrap;
}

.dossiers-page__pagination {
  margin-top: 1.5rem;
  display: flex;
  justify-content: center;
}
</style>
