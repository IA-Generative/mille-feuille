<script setup lang="ts">
/**
 * Extractions d'un document : la page avec ses rectangles à gauche, les entités de la page à droite, une recherche et
 * un filtre par entité au-dessus (ils proposent les pages concernées), et une pagination par page.
 */
import { computed, ref, toRef, watchEffect } from "vue";

import ExtractionEntityList from "@/components/dossiers/extraction/ExtractionEntityList.vue";
import ExtractionPageNav from "@/components/dossiers/extraction/ExtractionPageNav.vue";
import ExtractionPageViewer from "@/components/dossiers/extraction/ExtractionPageViewer.vue";
import ExtractionSearch from "@/components/dossiers/extraction/ExtractionSearch.vue";
import { useExtractionExplorer } from "@/composables/useExtractionExplorer";
import { useExtractionScreenshots } from "@/composables/useExtractionScreenshots";
import type { ExtractedDocument } from "@/types/dossierExtraction";

const props = defineProps<{ dossierId: string; document: ExtractedDocument }>();

const explorer = useExtractionExplorer(toRef(() => props.document.pages));
const screenshots = useExtractionScreenshots(
  () => props.dossierId,
  () => props.document.id,
);
const active = ref<number | null>(null);

// La page affichée est chargée à la demande ; revenir dessus ne la redemande pas.
watchEffect(() => {
  const page = explorer.current.value;
  if (page?.hasScreenshot) screenshots.load(page.id);
});

// Changer de page ou de filtre réinitialise la mise en avant : l'indice ne désigne plus la même entité.
watchEffect(() => {
  void explorer.pageIndex.value;
  void explorer.currentEntities.value;
  active.value = null;
});

const groups = computed(() =>
  explorer.currentEntities.value.map((entity, i) => ({ label: String(i + 1), boxes: entity.boxes })),
);
const url = computed(() => (explorer.current.value ? screenshots.urls[explorer.current.value.id] : undefined));
const status = computed(() => (explorer.current.value ? screenshots.state[explorer.current.value.id] : undefined));
</script>

<template>
  <div v-if="document.pages.length" class="extraction-explorer">
    <ExtractionSearch
      v-model:query="explorer.query.value"
      :names="explorer.names.value"
      :selected="explorer.selected.value"
      :filtering="explorer.filtering.value"
      :matching-pages="explorer.matchingPages.value"
      :current-index="explorer.pageIndex.value"
      @toggle="explorer.toggle"
      @goto="explorer.goTo"
      @reset="explorer.reset"
    />

    <ExtractionPageNav
      :index="explorer.pageIndex.value"
      :total="document.pages.length"
      :page-number="explorer.current.value.pageNumber"
      @goto="explorer.goTo"
    />

    <div class="extraction-explorer__columns">
      <section class="extraction-explorer__page" aria-label="Page du document">
        <ExtractionPageViewer
          v-if="url"
          :src="url"
          :alt="`Page ${explorer.current.value.pageNumber} du document`"
          :groups="groups"
          :active="active"
        />
        <p v-else-if="status === 'loading'" class="fr-text--sm extraction-explorer__muted">Chargement de la page…</p>
        <p v-else class="fr-text--sm extraction-explorer__muted">La capture de cette page n'est pas disponible.</p>
      </section>
      <section aria-label="Entités extraites de la page">
        <ExtractionEntityList
          :entities="explorer.currentEntities.value"
          :active="active"
          :filtering="explorer.filtering.value"
          @activate="active = $event"
        />
      </section>
    </div>
  </div>
  <p v-else class="fr-text--sm extraction-explorer__muted">Aucune page pour ce document.</p>
</template>

<style scoped>
.extraction-explorer {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.extraction-explorer__columns {
  display: grid;
  grid-template-columns: 3fr minmax(14rem, 2fr);
  gap: 1.5rem;
  align-items: start;
}

.extraction-explorer__page {
  position: sticky;
  top: 0;
}

.extraction-explorer__muted {
  color: var(--text-mention-grey);
}

@media (max-width: 48em) {
  .extraction-explorer__columns {
    grid-template-columns: 1fr;
  }

  .extraction-explorer__page {
    position: static;
  }
}
</style>
