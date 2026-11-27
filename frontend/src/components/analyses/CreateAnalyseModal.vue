<script setup lang="ts">
import { ref, watch } from "vue";

import LlmAssistButton from "@/components/analyses/LlmAssistButton.vue";
import AppModal from "@/components/AppModal.vue";
import CreationGroupsField from "@/components/groups/CreationGroupsField.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { useAuth } from "@/composables/useAuth";
import { ASSIST_MIN_WORDS_HINT, hasEnoughWords, suggestAnalyseDescription } from "@/composables/useLlmAssist";

const opened = defineModel<boolean>("opened", { default: false });
const emit = defineEmits<{ created: [id: string] }>();

const { create } = useAnalyses();
// Maquette (#657), montrée aux super admins : le choix des groupes n'est ni exigé ni envoyé.
const { isAdmin } = useAuth();
const mockGroupIds = ref<string[]>([]);

const name = ref("");
const description = ref("");
const isSuggesting = ref(false);

watch(opened, (isOpened) => {
  if (isOpened) {
    name.value = "";
    description.value = "";
    mockGroupIds.value = [];
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
  const analyse = await create(name.value.trim(), description.value.trim());
  opened.value = false;
  emit("created", analyse.id);
}
</script>

<template>
  <AppModal
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
    <CreationGroupsField v-if="isAdmin" v-model="mockGroupIds" />
    <LlmAssistButton
      label="Structurer la description avec le LLM"
      class="fr-mt-2w"
      :loading="isSuggesting"
      :disabled="!hasEnoughWords(description)"
      :disabled-hint="ASSIST_MIN_WORDS_HINT"
      @click="applySuggestion"
    />
  </AppModal>
</template>
