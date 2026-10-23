<script setup lang="ts">
import { computed, ref, watch } from "vue";

import MarkdownText from "@/components/MarkdownText.vue";
import PagerNav from "@/components/PagerNav.vue";
import { useReportsAdmin } from "@/composables/useReportsAdmin";
import { REPORT_STATUS_LABELS, REPORT_TYPE_LABELS, type ReportStatus, type ReportType } from "@/types/report";
import { API_BASE_URL } from "@/utils/api";

const { reports, pageCount, fetchList, updateReport } = useReportsAdmin();

const PAGE_SIZE = 10;
const currentPage = ref(1);
const statusFilter = ref<ReportStatus | "">("");
const typeFilter = ref<ReportType | "">("");

const statusFilterOptions = [
  { value: "", text: "Tous les statuts" },
  ...(Object.keys(REPORT_STATUS_LABELS) as ReportStatus[]).map((value) => ({
    value,
    text: REPORT_STATUS_LABELS[value],
  })),
];
const typeFilterOptions = [
  { value: "", text: "Tous les types" },
  ...(Object.keys(REPORT_TYPE_LABELS) as ReportType[]).map((value) => ({ value, text: REPORT_TYPE_LABELS[value] })),
];

function reload() {
  fetchList(currentPage.value, PAGE_SIZE, statusFilter.value || undefined, typeFilter.value || undefined);
}

watch(currentPage, reload, { immediate: true });
watch([statusFilter, typeFilter], () => {
  currentPage.value = 1;
  reload();
});


const statusBadgeType: Record<ReportStatus, "new" | "info" | "success" | "warning" | "error"> = {
  new: "new",
  in_progress: "info",
  resolved: "success",
  wont_fix: "warning",
};

// Brouillon de réponse par signalement, tant qu'il n'a pas été envoyé.
const draftResponses = ref<Record<string, string>>({});

function draftFor(reportId: string, current: string | null) {
  return draftResponses.value[reportId] ?? current ?? "";
}

async function setStatus(reportId: string, status: ReportStatus) {
  await updateReport(reportId, status, null);
}

async function submitResponse(reportId: string) {
  const response = (draftResponses.value[reportId] ?? "").trim();
  if (!response) return;
  await updateReport(reportId, "resolved", response);
  delete draftResponses.value[reportId];
}

const dateFormatter = new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" });
function formatDate(iso: string) {
  return dateFormatter.format(new Date(iso));
}

defineExpose({ reload });
</script>

<template>
  <section class="admin-reports">
    <h2 class="fr-h4">Signalements</h2>

    <div class="admin-reports__filters">
      <DsfrSelect v-model="statusFilter" label="Statut" label-visible :options="statusFilterOptions" />
      <DsfrSelect v-model="typeFilter" label="Type" label-visible :options="typeFilterOptions" />
    </div>

    <p v-if="reports.length === 0" class="fr-text--sm">Aucun signalement.</p>

    <ul v-else class="admin-reports__list">
      <li v-for="report in reports" :key="report.id" class="admin-reports__item">
        <div class="admin-reports__item-header">
          <div>
            <span class="admin-reports__item-title">{{ report.title }}</span>
            <p class="fr-text--sm admin-reports__item-meta">
              {{ REPORT_TYPE_LABELS[report.type] }} · {{ report.userDisplay }} · {{ formatDate(report.createdAt) }}
            </p>
          </div>
          <DsfrBadge :label="REPORT_STATUS_LABELS[report.status]" :type="statusBadgeType[report.status]" />
        </div>

        <MarkdownText :content="report.description" :lines="3" class="admin-reports__item-description" />

        <a
          v-if="report.hasScreenshot"
          :href="`${API_BASE_URL}/api/reports/${report.id}/screenshot`"
          target="_blank"
          rel="noopener noreferrer"
          class="fr-link fr-text--sm"
        >
          Voir la capture d'écran jointe
        </a>

        <div class="admin-reports__item-response">
          <DsfrInput
            :model-value="draftFor(report.id, report.adminResponse)"
            label="Réponse"
            label-visible
            is-textarea
            @update:model-value="(value: string) => (draftResponses[report.id] = value)"
          />
          <div class="admin-reports__item-actions">
            <DsfrButton label="Envoyer la réponse (marque comme résolu)" size="sm" @click="submitResponse(report.id)" />
            <DsfrButton
              v-if="report.status !== 'in_progress'"
              label="Marquer en cours"
              tertiary
              size="sm"
              @click="setStatus(report.id, 'in_progress')"
            />
            <DsfrButton
              v-if="report.status !== 'wont_fix'"
              label="Refuser"
              tertiary
              size="sm"
              @click="setStatus(report.id, 'wont_fix')"
            />
          </div>
        </div>
      </li>
    </ul>

    <PagerNav v-model:page="currentPage" :page-count="pageCount" class="admin-reports__pagination" />
  </section>
</template>

<style scoped>
.admin-reports {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.admin-reports__filters {
  display: flex;
  gap: 1rem;
  max-width: 30rem;
}

.admin-reports__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.admin-reports__item {
  padding: 1.25rem;
  background: var(--background-default-grey);
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.admin-reports__item-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.admin-reports__item-title {
  font-weight: 600;
}

.admin-reports__item-meta {
  margin: 0.25rem 0 0;
  color: var(--text-mention-grey);
}

.admin-reports__item-description {
  margin: 0;
  white-space: pre-wrap;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.admin-reports__item-response {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.admin-reports__item-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.admin-reports__pagination {
  display: flex;
  justify-content: center;
}
</style>
