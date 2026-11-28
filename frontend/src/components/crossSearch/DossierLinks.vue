<script setup lang="ts">
/** « À partir de dossiers » : choisir des dossiers, voir ce qui les relie et ce qui leur est lié. */
import { ref } from "vue";

import DossierPicker from "@/components/crossSearch/DossierPicker.vue";
import LinkExplorer from "@/components/crossSearch/LinkExplorer.vue";
import SelectionSummary from "@/components/crossSearch/SelectionSummary.vue";
import { MAX_ANCHORS, useDossierLinks } from "@/composables/useCrossSearch";

const chosenIds = defineModel<string[]>({ required: true });
const includeRelated = ref(true);

const { result, status, error, notice, retry } = useDossierLinks(chosenIds, includeRelated, (gone) => {
  chosenIds.value = chosenIds.value.filter((id) => !gone.includes(id));
});
const add = (id: string) => {
  if (chosenIds.value.length < MAX_ANCHORS) chosenIds.value = [...chosenIds.value, id];
};
</script>

<template>
  <DossierPicker v-model="chosenIds" :known="result?.dossiers ?? []" />
  <div class="fr-toggle fr-mb-2w">
    <input id="include-related" v-model="includeRelated" type="checkbox" class="fr-toggle__input" />
    <label class="fr-toggle__label" for="include-related">Montrer aussi les autres dossiers liés</label>
  </div>

  <div v-if="notice" class="fr-alert fr-alert--warning fr-alert--sm fr-mb-2w" role="status">
    <p>{{ notice }}</p>
  </div>

  <p v-if="!chosenIds.length" class="fr-text--sm">Choisissez un ou plusieurs dossiers pour voir ce qui les relie.</p>
  <p v-else-if="status === 'loading'" class="fr-text--sm" role="status">Recherche des liens…</p>
  <div v-else-if="status === 'error'" class="fr-alert fr-alert--error fr-alert--sm" role="alert">
    <p>{{ error }}</p>
    <DsfrButton label="Réessayer" size="sm" secondary @click="retry" />
  </div>
  <template v-else-if="result">
    <p v-if="!result.items.length" class="fr-text--sm" role="status">
      Rien ne relie ces dossiers (identifiants, valeurs extraites, documents).
    </p>
    <LinkExplorer v-slot="{ result: shown, select }" :result="result">
      <SelectionSummary :result="shown" @select="select" @add="add" />
    </LinkExplorer>
  </template>
</template>
