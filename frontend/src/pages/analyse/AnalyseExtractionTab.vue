<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";

import EntitiesEditor from "@/components/analyses/EntitiesEditor.vue";
import PromptEditor from "@/components/analyses/PromptEditor.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { useCanManageAnalyse } from "@/composables/useCanManageAnalyse";
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

// Labels et entités : le créateur et les administrateurs (le backend reste juge).
const canManageAnalyse = useCanManageAnalyse();
const readonly = computed(() => !analyse.value || !canManageAnalyse(analyse.value.createdBy));

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
    >
      <template #description>
        Ce prompt explique à l'agent IA comment extraire les informations clés de chaque document (nom, dates,
        numéros…) au format JSON. Pas encore de version en Markdown ? Décrivez votre besoin en quelques
        mots (3 mots minimum) dans la zone « Prompt (Markdown) », puis cliquez sur « Aide à la rédaction du prompt »,  sous la zone de texte :
        l'IA vous propose un prompt. Modifiez-le si besoin, puis cliquez sur « Enregistrer ». « Aperçu » montre le rendu en Markdown.
      </template>
    </PromptEditor>
    <hr class="analyse-tab__divider" />
    <EntitiesEditor
      :readonly="readonly"
      :entities="analyse.extraction.entities"
      :labels="analyse.classification.labels"
      :versions="analyse.extraction.entitiesVersions"
      @save="(entities) => updateExtractionEntities(analyse!.id, entities)"
      @restore="(versionId) => restoreExtractionEntitiesVersion(analyse!.id, versionId)"
    >
      <template #description>
        Listez ici les informations que l'IA doit extraire de chaque document (nom, date de naissance, numéro…).
        Donnez à chaque entité un nom, un type et une définition. « Suggérer des entités » propose une liste, qui
        remplace celle en cours de modification. Avec l'icône en forme de crayon, vous pouvez aussi choisir où chercher l'entité.
        Cliquez ensuite sur « Terminer », puis sur « Enregistrer » : « Terminer » seul n'enregistre pas.
      </template>
    </EntitiesEditor>
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
