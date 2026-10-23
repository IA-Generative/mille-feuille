<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useRoute } from "vue-router";

import SearchIndexOverview from "@/components/search/SearchIndexOverview.vue";
import SearchSettingsForm from "@/components/search/SearchSettingsForm.vue";
import { fetchEmbeddingModels, useAnalyseSearch } from "@/composables/useAnalyseSearch";
import type { SearchImpact, SearchSettings } from "@/types/search";

// Onglet « Recherche » d'une analyse : découpage des pages et modèle d'embeddings, versionnés, et l'état des index des
// dossiers. Changer un réglage laisse les dossiers déjà indexés servir avec leur index jusqu'à leur reconstruction.
const route = useRoute();
const analyseId = computed(() => String(route.params.id));
const { data, loading, error, embeddingModels, load, save, restore, preview, rebuildAll, refreshOverview } =
  useAnalyseSearch(analyseId);

const saving = ref(false);
const message = ref("");
const impact = ref<SearchImpact | null>(null);

let poll: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  load();
  fetchEmbeddingModels();
  // Les reconstructions avancent en arrière-plan : l'état des index se rafraîchit seul tant que la page est ouverte.
  poll = setInterval(refreshOverview, 10_000);
});
onBeforeUnmount(() => clearInterval(poll));

async function onChange(settings: SearchSettings) {
  impact.value = await preview(settings);
}

async function onSave(settings: SearchSettings) {
  saving.value = true;
  message.value = "";
  if (await save(settings)) message.value = "Réglages enregistrés. Les précédents sont dans l'historique.";
  impact.value = null;
  saving.value = false;
}

async function onRestore(versionId: string) {
  message.value = "";
  await restore(versionId);
  if (!error.value) message.value = "Version restaurée.";
  impact.value = null;
}

async function onRebuild() {
  message.value = "";
  if (await rebuildAll()) message.value = "Reconstruction lancée. Les dossiers gardent leur index actuel jusqu'à la bascule.";
}
</script>

<template>
  <div v-if="data">
    <SearchIndexOverview v-if="data.overview && data.overview.indexed > 0" :overview="data.overview" @rebuild="onRebuild" />
    <DsfrAlert v-if="data.problem" type="warning" small :description="data.problem" class="fr-mb-2w" />
    <SearchSettingsForm
      :settings="data.settings"
      :versions="data.versions"
      :embedding-models="embeddingModels"
      :impact="impact"
      :saving="saving"
      @change="onChange"
      @save="onSave"
      @restore="onRestore"
    />
    <p v-if="message" class="analyse-search__ok" role="status">{{ message }}</p>
    <p v-if="error" class="analyse-search__error" role="alert">{{ error }}</p>
  </div>
  <p v-else-if="loading">Chargement…</p>
  <p v-else-if="error" class="analyse-search__error" role="alert">{{ error }}</p>
</template>

<style scoped>
.analyse-search__ok {
  margin: 0.75rem 0 0;
  color: var(--text-default-success);
}

.analyse-search__error {
  margin: 0.75rem 0 0;
  color: var(--text-default-error);
}
</style>
