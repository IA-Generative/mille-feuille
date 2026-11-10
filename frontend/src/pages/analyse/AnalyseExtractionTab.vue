<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";

import EntitiesEditor from "@/components/analyses/EntitiesEditor.vue";
import PromptEditor from "@/components/analyses/PromptEditor.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { suggestExtractionPrompt } from "@/composables/useLlmAssist";

const route = useRoute();
const {
  getById,
  fetchAnalyse,
  updateExtractionPrompt,
  restoreExtractionPromptVersion,
  updateExtractionEntities,
  restoreExtractionEntitiesVersion,
} = useAnalyses();

const analyse = computed(() => getById(String(route.params.id)));

onMounted(() => {
  if (!analyse.value) fetchAnalyse(String(route.params.id));
});
</script>

<template>
  <div v-if="analyse">
    <PromptEditor
      :prompt="analyse.extraction.prompt"
      :versions="analyse.extraction.promptVersions"
      :suggest-prompt="suggestExtractionPrompt"
      @save="(prompt) => updateExtractionPrompt(analyse!.id, prompt)"
      @restore="(versionId) => restoreExtractionPromptVersion(analyse!.id, versionId)"
    />
    <hr class="analyse-tab__divider" />
    <EntitiesEditor
      :entities="analyse.extraction.entities"
      :labels="analyse.classification.labels"
      :versions="analyse.extraction.entitiesVersions"
      @save="(entities) => updateExtractionEntities(analyse!.id, entities)"
      @restore="(versionId) => restoreExtractionEntitiesVersion(analyse!.id, versionId)"
    />
  </div>
  <div v-else>
    <p>Chargement…</p>
  </div>
</template>

<style scoped>
.analyse-tab__divider {
  border: none;
  border-top: 1px solid var(--border-default-grey);
  margin: 1.5rem 0;
}
</style>
