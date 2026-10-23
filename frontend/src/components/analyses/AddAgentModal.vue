<script setup lang="ts">
import { computed, ref, watch } from "vue";

import LlmAssistButton from "@/components/analyses/LlmAssistButton.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { ASSIST_MIN_WORDS_HINT, hasEnoughWords, suggestAgentPrompt } from "@/composables/useLlmAssist";
import ModelPicker from "@/components/ModelPicker.vue";
import ToolSelectionField from "@/components/tools/ToolSelectionField.vue";
import { useTools } from "@/composables/useTools";

const props = defineProps<{ analyseId: string }>();
const opened = defineModel<boolean>("opened", { default: false });
const emit = defineEmits<{ created: [] }>();

const { addAgent } = useAnalyses();
const { defaultToolIds, fetchTools } = useTools();

const name = ref("");
const prompt = ref("");
// Les outils internes sont actifs par défaut pour un nouvel agent.
const toolIds = ref<string[]>([]);
const error = ref("");
const output = ref(true);
const model = ref("");
const isSuggesting = ref(false);

watch(opened, async (isOpened) => {
  if (isOpened) {
    await fetchTools();
    toolIds.value = defaultToolIds();
    error.value = "";
    name.value = "";
    prompt.value = "";
    output.value = true;
    model.value = "";
  }
});

async function applySuggestion(suggestionModel: string | null) {
  isSuggesting.value = true;
  try {
    prompt.value = await suggestAgentPrompt(prompt.value, suggestionModel);
  } catch (error) {
    alert(error instanceof Error ? error.message : "Échec de l'aide LLM.");
  } finally {
    isSuggesting.value = false;
  }
}

async function submit() {
  if (!name.value.trim() || !prompt.value.trim()) return;
  error.value = "";
  try {
    await addAgent(props.analyseId, name.value.trim(), prompt.value.trim(), toolIds.value, output.value, model.value || null);
  } catch (e) {
    // Un outil refusé (serveur inaccessible, tool désautorisé…) : on garde la fenêtre ouverte et on dit pourquoi.
    error.value = e instanceof Error ? e.message : "La création a échoué.";
    return;
  }
  opened.value = false;
  emit("created");
}
</script>

<template>
  <DsfrModal
    :opened="opened"
    @close="opened = false"
    title="Créer un agent"
    size="lg"
    :actions="[
      { label: 'Annuler', secondary: true, onClick: () => (opened = false) },
      { label: 'Créer', onClick: submit },
    ]"
  >
    <p class="fr-text--sm">
      Un agent réalise une tâche métier propre à cette analyse (contrôle de cohérence, rédaction d'une synthèse,
      construction d'une timeline...), à la différence de la classification et de l'extraction d'entités qui sont
      des analyses systématiques.
    </p>
    <DsfrInput v-model="name" label="Nom de l'agent" label-visible required />
    <DsfrInput
      v-model="prompt"
      label="Description (prompt)"
      label-visible
      is-textarea
      rows="10"
      required
      hint="Décris précisément le but de l'agent et le résultat attendu. Cette description sert de prompt au modèle de langage."
      class="fr-mt-2w"
    />
    <LlmAssistButton
      label="Structurer la description avec le LLM"
      class="fr-mt-2w"
      :loading="isSuggesting"
      :disabled="!hasEnoughWords(prompt)"
      :disabled-hint="ASSIST_MIN_WORDS_HINT"
      @click="applySuggestion"
    />
    <ToolSelectionField v-model="toolIds" class="fr-mt-2w" />
    <DsfrAlert v-if="error" type="error" small :description="error" class="fr-mt-2w" />
    <DsfrToggleSwitch
      v-model="output"
      label="Présenter le résultat de cet agent dans la page de résultat du dossier"
      class="fr-mt-2w"
    />
    <ModelPicker v-model="model" show-label block class="fr-mt-2w" />
  </DsfrModal>
</template>
