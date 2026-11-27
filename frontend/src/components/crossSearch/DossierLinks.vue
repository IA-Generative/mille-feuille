<script setup lang="ts">
/** « À partir de dossiers » : choisir des dossiers, voir ce qui les relie et ce qui leur est lié. */
import { computed, ref } from "vue";

import DossierPicker from "@/components/crossSearch/DossierPicker.vue";
import LinkExplorer from "@/components/crossSearch/LinkExplorer.vue";
import SelectionSummary from "@/components/crossSearch/SelectionSummary.vue";
import { mockLinksFrom } from "@/composables/useCrossSearch";

const chosenIds = defineModel<string[]>({ required: true });
const includeRelated = ref(true);

const result = computed(() => (chosenIds.value.length ? mockLinksFrom(chosenIds.value, includeRelated.value) : null));
const add = (id: string) => (chosenIds.value = [...chosenIds.value, id]);
</script>

<template>
  <DossierPicker v-model="chosenIds" />
  <div class="fr-toggle fr-mb-2w">
    <input id="include-related" v-model="includeRelated" type="checkbox" class="fr-toggle__input" />
    <label class="fr-toggle__label" for="include-related">Montrer aussi les autres dossiers liés</label>
  </div>

  <p v-if="!result" class="fr-text--sm">Choisissez un ou plusieurs dossiers pour voir ce qui les relie.</p>
  <template v-else>
    <p v-if="!result.items.length" class="fr-text--sm" role="status">
      Rien ne relie ces dossiers (personnes, entreprises, adresses, identifiants, documents, sujets).
    </p>
    <LinkExplorer v-slot="{ result: shown, select }" :result="result">
      <SelectionSummary :result="shown" @select="select" @add="add" />
    </LinkExplorer>
  </template>
</template>
