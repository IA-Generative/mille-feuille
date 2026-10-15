<script setup lang="ts">
import { computed, ref, toRef, watchEffect } from "vue";

import EntityDialog from "@/components/EntityDialog.vue";
import EntityList from "@/components/EntityList.vue";
import EntitySearch from "@/components/EntitySearch.vue";
import PageNavigator from "@/components/PageNavigator.vue";
import PageViewer from "@/components/PageViewer.vue";
import { usePageExplorer } from "@/composables/usePageExplorer";
import { usePageScreenshots } from "@/composables/usePageScreenshots";
import type { ExtractedPage } from "@/types";

const props = defineProps<{ runId: string; pages: ExtractedPage[] }>();

const explorer = usePageExplorer(
  toRef(props, "pages"),
  (page) => page.entities,
  (entity) => entity.value,
);
const screenshots = usePageScreenshots(() => props.runId);
const active = ref<number | null>(null);
const opened = ref<number | null>(null);

// La page affichée est chargée à la demande ; revenir dessus ne la redemande pas.
watchEffect(() => {
  const page = explorer.current.value;
  if (page?.has_screenshot) screenshots.load(page.page_id);
});

watchEffect(() => {
  // Changer de page ou de filtre réinitialise la mise en avant : l'indice ne désigne plus la même entité.
  void explorer.pageIndex.value;
  void explorer.currentItems.value;
  active.value = null;
  opened.value = null;
});

const groups = computed(() => explorer.currentItems.value.map((entity, i) => ({ label: String(i + 1), boxes: entity.boxes })));
const url = computed(() => (explorer.current.value ? screenshots.urls[explorer.current.value.page_id] : undefined));
const status = computed(() => (explorer.current.value ? screenshots.state[explorer.current.value.page_id] : undefined));
</script>

<template>
  <div v-if="pages.length" class="explorer">
    <EntitySearch
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
          :groups="groups"
          :active="active"
        />
        <p v-else-if="status === 'loading'" class="fr-text--sm muted">Chargement de la page…</p>
        <p v-else-if="status === 'failed' || !explorer.current.value.has_screenshot" class="fr-text--sm muted">
          La capture de cette page n'est pas disponible.
        </p>
      </section>
      <section class="entities-column" aria-label="Entités extraites de la page">
        <EntityList
          :entities="explorer.currentItems.value"
          :active="active"
          :filtering="explorer.filtering.value"
          @activate="active = $event"
          @open="opened = $event"
        />
      </section>
    </div>

    <EntityDialog
      v-if="opened !== null && explorer.currentItems.value[opened]"
      :entity="explorer.currentItems.value[opened]"
      :src="url"
      :page-number="explorer.current.value.page_number"
      @close="opened = null"
    />
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
  grid-template-columns: 3fr minmax(16rem, 2fr);
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
