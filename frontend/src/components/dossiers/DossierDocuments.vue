<script setup lang="ts">
import { computed, ref } from "vue";

import MarkdownText from "@/components/MarkdownText.vue";
import type { DocumentSource } from "@/types/documentSource";
import {
  SUMMARY_STATUS_LABELS,
  TEXT_EXTRACTION_STATUS_LABELS,
  type DossierDocument,
  type SummaryStatus,
  type TextExtractionStatus,
} from "@/types/dossier";

const props = defineProps<{
  documents: DossierDocument[];
  /** Affiche les contrôles de régénération des résumés (page détail uniquement). */
  showSummaryActions?: boolean;
  /** Sources proposées pour le dossier : active le changement de source d'un document. */
  sources?: DocumentSource[];
  /** Affiche le bouton « Ajouter des documents ». */
  canAdd?: boolean;
}>();

const emit = defineEmits<{
  regenerateSummary: [documentId: string];
  add: [];
  changeSource: [documentId: string, sourceId: string | null];
}>();

// Un seul document en cours de changement de source à la fois.
const editingSourceId = ref<string | undefined>(undefined);

function onSourcePicked(documentId: string, value: string) {
  editingSourceId.value = undefined;
  emit("changeSource", documentId, value || null);
}

const statusBadgeType: Record<TextExtractionStatus, "new" | "info" | "success" | "error"> = {
  en_attente: "new",
  en_cours: "info",
  terminé: "success",
  échec: "error",
};

const statusIcon: Record<TextExtractionStatus, string> = {
  en_attente: "ri-time-line",
  en_cours: "ri-loader-4-line",
  terminé: "ri-check-line",
  échec: "ri-error-warning-line",
};

const summaryBadgeType: Record<SummaryStatus, "new" | "info" | "success" | "error"> = {
  en_attente: "new",
  en_cours: "info",
  terminé: "success",
  échec: "error",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function fileIcon(mimetype: string): string {
  if (mimetype.startsWith("image/")) return "ri-image-line";
  if (mimetype === "application/pdf") return "ri-file-pdf-line";
  return "ri-file-line";
}

const hasActiveExtraction = computed(() =>
  props.documents.some((d) => d.textExtractionStatus === "en_cours" || d.textExtractionStatus === "en_attente"),
);

// Accordéon : un document déplié à la fois (par id).
const expandedDocId = ref<string | undefined>(undefined);

function toggleSummary(docId: string) {
  expandedDocId.value = expandedDocId.value === docId ? undefined : docId;
}
</script>

<template>
  <section v-if="documents.length > 0" class="dossier-documents">
    <div class="dossier-documents__header">
      <h2 class="fr-h6">Documents</h2>
      <span v-if="hasActiveExtraction" class="dossier-documents__hint fr-text--xs">
        Extraction de texte en cours…
      </span>
      <DsfrButton
        v-if="canAdd"
        label="Ajouter des documents"
        icon="ri-add-line"
        size="sm"
        secondary
        class="dossier-documents__add"
        @click="emit('add')"
      />
    </div>

    <ul class="dossier-documents__list">
      <li v-for="document in documents" :key="document.id" class="dossier-documents__item">
        <div class="dossier-documents__row">
          <span class="dossier-documents__icon">
            <VIcon :name="fileIcon(document.mimetype)" />
          </span>

          <div class="dossier-documents__info">
            <span class="dossier-documents__name">{{ document.name }}</span>
            <span class="fr-text--xs dossier-documents__meta">{{ formatSize(document.size) }}</span>
            <DsfrBadge
              v-if="document.label"
              :label="document.label"
              type="info"
              small
              class="dossier-documents__label"
            />
            <!-- Un seul bloc sur une ligne ; le bouton reste dans le DOM (v-show) : s'il disparaissait au clic, la
                 modale le prendrait pour un clic à l'extérieur et se fermerait. -->
            <span class="dossier-documents__source-row">
              <span
                v-if="document.source && editingSourceId !== document.id"
                class="fr-text--xs dossier-documents__source"
                :title="document.source.description || undefined"
              >
                <VIcon name="ri-inbox-archive-line" />
                {{ document.source.name }}
              </span>
              <template v-if="sources">
                <select
                  v-if="editingSourceId === document.id"
                  class="fr-select dossier-documents__source-select"
                  aria-label="Source du fichier"
                  :value="document.source?.id ?? ''"
                  @change="onSourcePicked(document.id, ($event.target as HTMLSelectElement).value)"
                >
                  <option value="">Sans source</option>
                  <option v-for="source in sources" :key="source.id" :value="source.id">{{ source.name }}</option>
                </select>
                <button
                  v-show="editingSourceId !== document.id"
                  type="button"
                  class="fr-link fr-text--xs dossier-documents__source-edit"
                  @click="editingSourceId = document.id"
                >
                  {{ document.source ? "Changer la source" : "Ajouter une source" }}
                </button>
              </template>
            </span>
          </div>

          <div class="dossier-documents__status">
            <VIcon
              :name="statusIcon[document.textExtractionStatus]"
              :class="{ 'dossier-documents__spinner': document.textExtractionStatus === 'en_cours' }"
            />
            <DsfrBadge
              :label="TEXT_EXTRACTION_STATUS_LABELS[document.textExtractionStatus]"
              :type="statusBadgeType[document.textExtractionStatus]"
              small
            />
          </div>
        </div>

        <!-- Résumé du document (issue #52) -->
        <div v-if="document.summaryStatus !== 'en_attente' || document.summary" class="dossier-documents__summary">
          <button
            type="button"
            class="dossier-documents__summary-toggle"
            @click="toggleSummary(document.id)"
          >
            <VIcon name="ri-file-text-line" />
            <DsfrBadge
              :label="SUMMARY_STATUS_LABELS[document.summaryStatus]"
              :type="summaryBadgeType[document.summaryStatus]"
              small
            />
            <VIcon
              :name="expandedDocId === document.id ? 'ri-arrow-up-s-line' : 'ri-arrow-down-s-line'"
              class="dossier-documents__summary-chevron"
            />
          </button>

          <div v-if="expandedDocId === document.id" class="dossier-documents__summary-body">
            <div v-if="document.summaryStatus === 'en_cours'" class="dossier-documents__summary-loading">
              <VIcon name="ri-loader-4-line" class="dossier-documents__spinner" />
              <span class="fr-text--xs">Génération du résumé en cours…</span>
            </div>
            <div v-else-if="document.summaryStatus === 'échec'" class="dossier-documents__summary-error">
              <VIcon name="ri-error-warning-line" />
              <span class="fr-text--xs">{{ document.summaryError ?? "Erreur lors de la génération du résumé" }}</span>
            </div>
            <MarkdownText v-else-if="document.summary" :content="document.summary.content" />
            <p v-else class="fr-text--xs dossier-documents__summary-empty">Aucun résumé disponible.</p>

            <button
              v-if="showSummaryActions && document.summaryStatus !== 'en_cours'"
              type="button"
              class="fr-link fr-text--xs dossier-documents__regenerate"
              @click="emit('regenerateSummary', document.id)"
            >
              <VIcon name="ri-refresh-line" />
              Régénérer le résumé
            </button>
          </div>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.dossier-documents {
  margin-bottom: 1.5rem;
}

.dossier-documents__header {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.dossier-documents__header h2 {
  margin: 0;
}

.dossier-documents__add {
  margin-left: auto;
}

.dossier-documents__source-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
}

.dossier-documents__source {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  color: var(--text-mention-grey);
}

.dossier-documents__source-select {
  width: auto;
  max-width: 14rem;
  padding-block: 0.25rem;
}

.dossier-documents__source-edit {
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
}

.dossier-documents__hint {
  color: var(--text-mention-grey);
}

.dossier-documents__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.dossier-documents__item {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-default-grey);
}

.dossier-documents__row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.dossier-documents__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 0.375rem;
  background: var(--background-alt-grey);
  color: var(--text-default-grey);
  flex-shrink: 0;
  font-size: 1.25rem;
}

.dossier-documents__info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
}

.dossier-documents__name {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dossier-documents__meta {
  color: var(--text-mention-grey);
}

.dossier-documents__label {
  align-self: flex-start;
}

.dossier-documents__status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.dossier-documents__spinner {
  animation: spin 1s linear infinite;
}

/* --- Résumé du document (issue #52) --- */

.dossier-documents__summary {
  margin-top: 0.5rem;
  border-top: 1px solid var(--border-default-grey);
  padding-top: 0.5rem;
}

.dossier-documents__summary-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0.25rem 0;
  color: var(--text-default-grey);
  width: 100%;
}

.dossier-documents__summary-toggle:hover {
  color: var(--text-action-high-blue-france);
}

.dossier-documents__summary-chevron {
  margin-left: auto;
}

.dossier-documents__summary-body {
  padding: 0.5rem 0 0.25rem;
}

.dossier-documents__summary-loading,
.dossier-documents__summary-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-mention-grey);
}

.dossier-documents__summary-empty {
  color: var(--text-mention-grey);
  margin: 0;
}

.dossier-documents__regenerate {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  margin-top: 0.5rem;
  cursor: pointer;
  background: transparent;
  border: none;
  padding: 0;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
