<script setup lang="ts">
import { ref, watch } from "vue";

import LlmAssistButton from "@/components/analyses/LlmAssistButton.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { ASSIST_MIN_WORDS_HINT, hasEnoughWords, suggestAnalyseDescription } from "@/composables/useLlmAssist";

const opened = defineModel<boolean>("opened", { default: false });
const emit = defineEmits<{ created: [] }>();

const { create } = useAnalyses();

const name = ref("");
const description = ref("");
const isSuggesting = ref(false);

watch(opened, (isOpened) => {
  if (isOpened) {
    name.value = "";
    description.value = "";
  }
});

async function applySuggestion(suggestionModel: string | null) {
  isSuggesting.value = true;
  try {
    description.value = await suggestAnalyseDescription(description.value, suggestionModel);
  } catch (error) {
    alert(error instanceof Error ? error.message : "Échec de l'aide LLM.");
  } finally {
    isSuggesting.value = false;
  }
}

async function submit() {
  if (!name.value.trim() || !description.value.trim()) return;
  await create(name.value.trim(), description.value.trim());
  opened.value = false;
  emit("created");
}
</script>

<template>
  <DsfrModal
    :opened="opened"
    @close="opened = false"
    title="Créer une analyse"
    :actions="[
      { label: 'Annuler', secondary: true, onClick: () => (opened = false) },
      { label: 'Créer', onClick: submit },
    ]"
  >
    <DsfrInput v-model="name" label="Nom de l'analyse" label-visible required />
    <DsfrInput
      v-model="description"
      label="Description"
      label-visible
      is-textarea
      required
      hint="Décris le but métier de l'analyse : contexte, objectif, documents concernés et résultat attendu."
      class="fr-mt-2w"
    />
    <LlmAssistButton
      label="Structurer la description avec le LLM"
      class="fr-mt-2w"
      :loading="isSuggesting"
      :disabled="!hasEnoughWords(description)"
      :disabled-hint="ASSIST_MIN_WORDS_HINT"
      @click="applySuggestion"
    />
  </DsfrModal>
</template>
