<script setup lang="ts">
/** Résultats d'extraction d'un dossier : un explorateur par document (page, entités, recherche, filtre, pagination). */
import { computed, onMounted, ref, watch } from "vue";

import ExtractionExplorer from "@/components/dossiers/extraction/ExtractionExplorer.vue";
import { useDossierExtractions } from "@/composables/useDossierExtractions";

const props = defineProps<{ dossierId: string }>();

const { documents, isLoading, error, load } = useDossierExtractions(props.dossierId);
const selectedId = ref<string | undefined>(undefined);

const selected = computed(() => documents.value.find((d) => d.id === selectedId.value) ?? documents.value[0]);

// Le sélecteur démarre sur le premier document (sans valeur, il s'afficherait vide).
watch(documents, (all) => {
  if (!selectedId.value && all.length) selectedId.value = all[0].id;
});

onMounted(load);
</script>

<template>
  <div class="extraction-results">
    <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
    <p v-else-if="isLoading" class="fr-text--sm extraction-results__muted" aria-live="polite">Chargement…</p>
    <p v-else-if="!documents.length" class="fr-text--sm extraction-results__muted">Aucun document pour le moment.</p>

    <template v-else>
      <div v-if="documents.length > 1" class="fr-select-group">
        <label class="fr-label" for="extraction-document">Document</label>
        <select id="extraction-document" v-model="selectedId" class="fr-select">
          <option v-for="document in documents" :key="document.id" :value="document.id">{{ document.name }}</option>
        </select>
      </div>
      <h3 v-else class="fr-text--md extraction-results__title">{{ documents[0].name }}</h3>

      <ExtractionExplorer :key="selected.id" :dossier-id="dossierId" :document="selected" />
    </template>
  </div>
</template>

<style scoped>
.extraction-results {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.extraction-results__title {
  margin: 0;
}

.extraction-results__muted {
  color: var(--text-mention-grey);
}
</style>
