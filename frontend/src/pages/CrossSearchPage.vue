<script setup lang="ts">
import { ref } from "vue";

import DossierLinks from "@/components/crossSearch/DossierLinks.vue";
import LinkExplorer from "@/components/crossSearch/LinkExplorer.vue";
import ResemblanceBoard from "@/components/crossSearch/ResemblanceBoard.vue";
import ResultList from "@/components/crossSearch/ResultList.vue";
import { useCrossSearch } from "@/composables/useCrossSearch";

type Mode = "keywords" | "dossiers" | "resemblances";
const MODES: { value: Mode; label: string }[] = [
  { value: "keywords", label: "Par mots-clés" },
  { value: "dossiers", label: "À partir de dossiers" },
  { value: "resemblances", label: "Rapprochements" },
];

const { result, search } = useCrossSearch();

const mode = ref<Mode>("keywords");
const input = ref("");
const chosenIds = ref<string[]>([]);

// La recherche n'est pas mise dans l'URL : les mots cherchés sont souvent des noms de personnes.
const onSearch = () => search(input.value);

function explore(ids: string[]) {
  chosenIds.value = [...ids];
  mode.value = "dossiers";
}
</script>

<template>
  <div>
    <h1 class="fr-h2">Recherche</h1>
    <p class="fr-text--lead">Cherchez dans tous vos dossiers et voyez ce qui les relie.</p>
    <div class="fr-alert fr-alert--info fr-mb-3w" role="note">
      <p class="fr-alert__title">Fonctionnalité bientôt disponible</p>
      <p>
        Ceci est un aperçu : les dossiers, les personnes et les liens affichés sont des <strong>données fictives</strong>.
        La recherche ne porte pas encore sur vos dossiers.
      </p>
    </div>

    <fieldset class="fr-segmented fr-mb-3w">
      <legend class="fr-segmented__legend fr-sr-only">Point de départ</legend>
      <div class="fr-segmented__elements">
        <div v-for="option in MODES" :key="option.value" class="fr-segmented__element">
          <input :id="`mode-${option.value}`" v-model="mode" type="radio" name="cross-search-mode" :value="option.value" />
          <label class="fr-label" :for="`mode-${option.value}`">{{ option.label }}</label>
        </div>
      </div>
    </fieldset>

    <!-- v-show : changer d'onglet garde la recherche, ses filtres et sa sélection. -->
    <div v-show="mode === 'keywords'">
      <DsfrSearchBar
        label="Mots-clés"
        placeholder="Un nom, une adresse, une immatriculation…"
        :model-value="input"
        class="cross-search__bar"
        @update:model-value="input = $event"
        @search="onSearch"
      />

      <p v-if="!result" class="fr-text--sm">Saisissez des mots-clés puis lancez la recherche. Essayez « exemple » ou « lilas ».</p>
      <p v-else-if="!result.dossiers.length" class="fr-text--sm" role="status">
        Aucun dossier accessible ne correspond à « {{ result.query }} ».
      </p>
      <template v-else>
        <p class="fr-text--sm" role="status">
          {{ result.dossiers.length }} dossier(s) trouvé(s), {{ result.items.length }} point(s) commun(s).
        </p>
        <LinkExplorer v-slot="{ result: shown, select }" :result="result">
          <ResultList :dossiers="shown.dossiers" @select="select({ type: 'node', id: $event })" @explore="explore" />
        </LinkExplorer>
      </template>
    </div>

    <!-- v-if : le graphe a besoin d'un cadre visible pour connaître sa taille. -->
    <DossierLinks v-if="mode === 'dossiers'" v-model="chosenIds" />
    <ResemblanceBoard v-if="mode === 'resemblances'" @explore="explore" />
  </div>
</template>

<style scoped>
.cross-search__bar {
  max-width: 40rem;
  margin-bottom: 1.5rem;
}
</style>
