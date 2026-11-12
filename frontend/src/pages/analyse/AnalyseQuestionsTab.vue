<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import FrequentQuestionsEditor from "@/components/analyses/FrequentQuestionsEditor.vue";
import VersionHistory from "@/components/analyses/VersionHistory.vue";
import { useAnalyseQuestions } from "@/composables/useAnalyseQuestions";

// Onglet « Questions » d'une analyse : les questions fréquentes dont chaque dossier reçoit la réponse une fois analysé.
// Versionnées comme le reste ; un dossier déjà analysé reçoit la réponse aux nouvelles questions à sa relance.
const route = useRoute();
const analyseId = computed(() => String(route.params.id));
const { data, loading, error, load, save, restore } = useAnalyseQuestions(analyseId);

const message = ref("");
const saving = ref(false);

onMounted(load);

async function onSave(questions: string[]) {
  message.value = "";
  saving.value = true;
  if (await save(questions)) message.value = "Questions enregistrées. La liste précédente est dans l'historique.";
  saving.value = false;
}

async function onRestore(versionId: string) {
  message.value = "";
  if (await restore(versionId)) message.value = "Version restaurée.";
}

const formatVersion = (content: { questions: string[] }) =>
  content.questions.length === 0 ? "Aucune question" : content.questions.map((question) => `• ${question}`).join("\n");
</script>

<template>
  <div v-if="data" class="analyse-questions">
    <p class="fr-text--sm">
      Ces questions reçoivent leur réponse pour chaque dossier de l'analyse, une fois son analyse terminée : elles sont
      proposées en tête de la conversation, avec leur réponse déjà prête. Une question dont le dossier ne contient pas la
      réponse n'est pas proposée. Un dossier déjà analysé reçoit la réponse aux nouvelles questions à sa relance.
    </p>
    <FrequentQuestionsEditor :model-value="data.questions" :saving="saving" @save="onSave" />
    <VersionHistory :versions="data.versions" :format-content="formatVersion" @restore="onRestore" />
    <p v-if="message" class="analyse-questions__ok" role="status">{{ message }}</p>
    <DsfrAlert v-if="error" alert type="error" small :description="error" />
  </div>
  <p v-else-if="loading">Chargement…</p>
  <DsfrAlert v-else-if="error" alert type="error" small :description="error" />
</template>

<style scoped>
.analyse-questions {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.analyse-questions p {
  margin: 0;
}

.analyse-questions__ok {
  color: var(--text-default-success);
}
</style>
