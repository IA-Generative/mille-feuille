<script setup lang="ts">
import { computed, toRef, watchEffect } from "vue";

import EntitySearch from "@/components/EntitySearch.vue";
import LabelList from "@/components/LabelList.vue";
import PageNavigator from "@/components/PageNavigator.vue";
import PageViewer from "@/components/PageViewer.vue";
import { usePageExplorer } from "@/composables/usePageExplorer";
import { usePageScreenshots } from "@/composables/usePageScreenshots";
import type { ClassifiedPage } from "@/types";

const props = defineProps<{ runId: string; pages: ClassifiedPage[] }>();

// Une classification vaut pour la page entière : pas de rectangle, la recherche porte sur le nom du label.
const explorer = usePageExplorer(
  toRef(props, "pages"),
  (page) => page.labels,
  (label) => label.name,
);
const screenshots = usePageScreenshots(() => props.runId);

watchEffect(() => {
  const page = explorer.current.value;
  if (page?.has_screenshot) screenshots.load(page.page_id);
});

const url = computed(() => (explorer.current.value ? screenshots.urls[explorer.current.value.page_id] : undefined));
const status = computed(() => (explorer.current.value ? screenshots.state[explorer.current.value.page_id] : undefined));
</script>

<template>
  <div v-if="pages.length" class="explorer">
    <EntitySearch
      v-model:query="explorer.query.value"
      placeholder="Rechercher une classification"
      filter-label="Filtrer par classification"
      :names="explorer.names.value"
      :selected="explorer.selected.value"
      :filtering="explorer.filtering.value"
      :matching-pages="explorer.matchingPages.value"
      :current-index="explorer.pageIndex.value"
      @toggle="explorer.toggle"
      @goto="explorer.goTo"
      @reset="explorer.reset"
    />

    <PageNavigator
      :index="explorer.pageIndex.value"
      :total="pages.length"
      :page-number="explorer.current.value.page_number"
      @goto="explorer.goTo"
    />

    <div class="columns">
      <section class="page-column" aria-label="Page du document">
        <PageViewer
          v-if="url"
          :src="url"
          :alt="`Page ${explorer.current.value.page_number} du document`"
          :groups="[]"
          :active="null"
        />
        <p v-else-if="status === 'loading'" class="fr-text--sm muted">Chargement de la page…</p>
        <p v-else class="fr-text--sm muted">La capture de cette page n'est pas disponible.</p>
      </section>
      <section aria-label="Classification de la page">
        <LabelList :labels="explorer.currentItems.value" :filtering="explorer.filtering.value" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.explorer {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.columns {
  display: grid;
  grid-template-columns: 3fr minmax(14rem, 2fr);
  gap: 1.5rem;
  align-items: start;
}
.page-column {
  position: sticky;
  top: 1rem;
}
.muted {
  color: var(--text-mention-grey);
}
@media (max-width: 48em) {
  .columns {
    grid-template-columns: 1fr;
  }
  .page-column {
    position: static;
  }
}
</style>
