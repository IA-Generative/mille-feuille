<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import type { ChatWindowSource } from "@/components/ChatWindow.vue";
import { type ResultKind, type ResultRow, useDossierResults } from "@/composables/useDossierResults";

const props = defineProps<{ dossierId: string; kind: ResultKind }>();
const emit = defineEmits<{ viewPage: [source: ChatWindowSource] }>();

const { breakdown, rows, total, pageCount, isLoading, error, loadBreakdown, loadRows } = useDossierResults(
  props.dossierId,
);

const isLabel = computed(() => props.kind === "label");
const unitLabel = computed(() => (isLabel.value ? "classification" : "entité"));

// DsfrPagination travaille avec un index de page commençant à 0.
const pageIndex = ref(0);
const pages = computed(() =>
  Array.from({ length: pageCount.value }, (_, i) => ({ label: String(i + 1), title: `Page ${i + 1}` })),
);

function pagesLabel(row: ResultRow): string {
  const numbers = row.pages.map((p) => p.pageNumber);
  return `${numbers.length > 1 ? "pages" : "page"} ${numbers.join(", ")}`;
}

/** Ouvre la page source du résultat (capture, zones encadrées, texte) dans la modale de source du chat. */
function viewPage(row: ResultRow) {
  emit("viewPage", {
    id: row.id,
    excerpt: isLabel.value ? undefined : row.value,
    pages: row.pages,
    dossierDocumentId: row.documentId,
    boundingBoxes: row.boundingBoxes,
  });
}

onMounted(() => {
  loadBreakdown();
  loadRows(props.kind, 1);
});
watch(pageIndex, (index) => loadRows(props.kind, index + 1));
</script>

<template>
  <div class="results-detail">
    <section v-if="breakdown.length" aria-label="Répartition par fichier">
      <h3 class="fr-text--md results-detail__title">Répartition par fichier</h3>
      <ul class="results-detail__files">
        <li v-for="file in breakdown" :key="file.documentId" class="results-detail__file">
          <span class="results-detail__file-name">{{ file.documentName }}</span>
          <span class="fr-text--sm results-detail__muted">
            <template v-if="isLabel">{{ file.classifiedPageCount }}/{{ file.pageCount }} page(s) classifiée(s)</template>
            <template v-else>{{ file.entityCount }} entité(s) · {{ file.pageCount }} page(s)</template>
          </span>
        </li>
      </ul>
    </section>

    <section aria-label="Détail">
      <h3 class="fr-text--md results-detail__title">
        {{ isLabel ? "Classifications" : "Entités" }}
        <span class="fr-text--sm results-detail__muted">({{ total }})</span>
      </h3>

      <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
      <p v-else-if="!isLoading && !rows.length" class="fr-text--sm results-detail__muted">
        Aucune {{ unitLabel }} pour le moment.
      </p>

      <ul v-else class="results-detail__rows" :aria-busy="isLoading">
        <li v-for="row in rows" :key="row.id" class="results-detail__row">
          <div class="results-detail__row-main">
            <span v-if="!isLabel" class="fr-text--sm results-detail__muted">{{ row.name }}</span>
            <span class="results-detail__value">{{ row.value }}</span>
          </div>
          <div class="fr-text--sm results-detail__muted results-detail__row-meta">
            <span>{{ row.documentName }} · {{ pagesLabel(row) }}</span>
            <span v-if="row.confidence !== undefined">{{ Math.round(row.confidence * 100) }}%</span>
          </div>
          <button type="button" class="fr-link fr-text--sm results-detail__view" @click="viewPage(row)">
            <VIcon name="ri-file-text-line" scale="0.8" />
            Voir la page
          </button>
        </li>
      </ul>

      <DsfrPagination v-if="pageCount > 1" v-model:current-page="pageIndex" :pages="pages" />
    </section>
  </div>
</template>

<style scoped>
.results-detail {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.results-detail__title {
  margin: 0 0 0.5rem;
  font-weight: bold;
}

.results-detail__muted {
  margin: 0;
  color: var(--text-mention-grey);
}

.results-detail__files,
.results-detail__rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.results-detail__file,
.results-detail__row {
  margin: 0;
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--border-default-grey);
}

.results-detail__file {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
}

.results-detail__file-name {
  margin: 0;
  overflow-wrap: anywhere;
}

.results-detail__row-main {
  display: flex;
  flex-direction: column;
}

.results-detail__value {
  margin: 0;
  font-weight: bold;
  overflow-wrap: anywhere;
}

.results-detail__view {
  margin: 0.35rem 0 0;
  padding: 0;
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  background: transparent;
  border: none;
  cursor: pointer;
}

.results-detail__row-meta {
  margin: 0;
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: 0.15rem;
}
</style>
