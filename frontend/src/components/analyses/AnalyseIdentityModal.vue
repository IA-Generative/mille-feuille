<script setup lang="ts">
/**
 * Modifier le nom et la description d'une analyse, avec l'historique de chacun (restauration). Quand le créateur ou
 * un administrateur veut la supprimer, la modale le dit au parent (`delete`) : la confirmation est une autre modale.
 */
import { ref, watch } from "vue";

import LlmAssistButton from "@/components/analyses/LlmAssistButton.vue";
import VersionHistory from "@/components/analyses/VersionHistory.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { ASSIST_MIN_WORDS_HINT, hasEnoughWords, suggestAnalyseDescription } from "@/composables/useLlmAssist";
import type { Analyse } from "@/types/analyse";
import { userMessage } from "@/utils/api";

const props = defineProps<{ analyse: Analyse }>();
const opened = defineModel<boolean>("opened", { default: false });
const emit = defineEmits<{ delete: [] }>();

const { updateIdentity, restoreNameVersion, restoreDescriptionVersion } = useAnalyses();

const name = ref("");
const description = ref("");
const isSuggesting = ref(false);
const error = ref("");

// À chaque ouverture (et quand une restauration change l'analyse), les champs repartent de la valeur courante.
watch(
  () => [opened.value, props.analyse.name, props.analyse.description] as const,
  ([isOpened]) => {
    if (!isOpened) return;
    name.value = props.analyse.name;
    description.value = props.analyse.description;
    error.value = "";
  },
  { immediate: true },
);

async function applySuggestion(model: string | null) {
  isSuggesting.value = true;
  try {
    description.value = await suggestAnalyseDescription(description.value, model);
  } catch (failure) {
    error.value = userMessage(failure, "Échec de l'aide LLM.");
  } finally {
    isSuggesting.value = false;
  }
}

async function run(action: () => Promise<void>) {
  error.value = "";
  try {
    await action();
  } catch (failure) {
    error.value = userMessage(failure, "Échec de l'enregistrement.");
  }
}

async function save() {
  if (!name.value.trim() || !description.value.trim()) {
    error.value = "Le nom et la description sont obligatoires.";
    return;
  }
  await run(async () => {
    await updateIdentity(props.analyse.id, name.value.trim(), description.value.trim());
    opened.value = false;
  });
}
</script>

<template>
  <DsfrModal
    :opened="opened"
    title="Modifier l'analyse"
    @close="opened = false"
    :actions="[
      { label: 'Annuler', secondary: true, onClick: () => (opened = false) },
      { label: 'Enregistrer', onClick: save },
    ]"
  >
    <DsfrInput v-model="name" label="Nom de l'analyse" label-visible required />
    <VersionHistory
      :versions="analyse.nameVersions"
      :format-content="(content: string) => content"
      @restore="(versionId: string) => run(() => restoreNameVersion(analyse.id, versionId))"
    />

    <DsfrInput
      v-model="description"
      label="Description"
      label-visible
      is-textarea
      required
      hint="Décris le but métier de l'analyse : elle sert d'instruction aux agents."
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
    <VersionHistory
      :versions="analyse.descriptionVersions"
      :format-content="(content: string) => content"
      markdown
      @restore="(versionId: string) => run(() => restoreDescriptionVersion(analyse.id, versionId))"
    />

    <DsfrAlert v-if="error" alert type="error" small :description="error" class="fr-mt-2w" />

    <hr class="analyse-identity__divider" />
    <DsfrButton label="Supprimer l'analyse" icon="ri-delete-bin-line" tertiary size="sm" @click="emit('delete')" />
  </DsfrModal>
</template>

<style scoped>
.analyse-identity__divider {
  border: none;
  border-top: 1px solid var(--border-default-grey);
  margin: 1.5rem 0 1rem;
}
</style>
