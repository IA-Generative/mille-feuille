<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import SourcesEditor from "@/components/analyses/SourcesEditor.vue";
import {
  createAnalyseSource,
  deleteSource,
  fetchAnalyseSources,
  updateSource,
} from "@/composables/useDocumentSources";
import type { DocumentSource } from "@/types/documentSource";

// Onglet « Sources » d'une analyse : les sources proposées au dépôt d'un fichier dans ses dossiers.
const analyseId = String(useRoute().params.id);

const sources = ref<DocumentSource[]>([]);
const busy = ref(false);
const error = ref("");

async function load() {
  sources.value = await fetchAnalyseSources(analyseId).catch(() => []);
}

async function run(operation: () => Promise<unknown>) {
  busy.value = true;
  error.value = "";
  try {
    await operation();
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "L'opération a échoué.";
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section>
    <h2 class="fr-h4">Sources des fichiers</h2>
    <p class="fr-text--sm">
      D'où viennent les fichiers déposés dans les dossiers de cette analyse (courrier, guichet, autre administration…).
      La description est transmise à l'IA avec chaque document.
    </p>
    <DsfrAlert v-if="error" type="error" :title="error" small class="fr-mb-2w" />
    <SourcesEditor
      :sources="sources"
      :busy="busy"
      @create="run(() => createAnalyseSource(analyseId, $event))"
      @update="(id, input) => run(() => updateSource(id, input))"
      @remove="run(() => deleteSource($event))"
    />
  </section>
</template>
