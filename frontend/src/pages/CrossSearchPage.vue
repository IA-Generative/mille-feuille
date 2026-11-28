<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import DossierLinks from "@/components/crossSearch/DossierLinks.vue";
import LinkExplorer from "@/components/crossSearch/LinkExplorer.vue";
import ResemblanceBoard from "@/components/crossSearch/ResemblanceBoard.vue";
import ResultList from "@/components/crossSearch/ResultList.vue";
import { MAX_ANCHORS, MIN_QUERY_LENGTH, useCrossSearch } from "@/composables/useCrossSearch";

type Mode = "keywords" | "dossiers" | "resemblances";
const MODES: { value: Mode; label: string }[] = [
  { value: "keywords", label: "Par mots-clés" },
  { value: "dossiers", label: "À partir de dossiers" },
  { value: "resemblances", label: "Rapprochements" },
];

const route = useRoute();
const router = useRouter();
const { result, total, status, error, search, retry } = useCrossSearch();

/** La sélection de départ est dans l'adresse (des identifiants) : on la retrouve en revenant d'un dossier ouvert. */
const fromUrl = String(route.query.dossiers ?? "")
  .split(",")
  .filter(Boolean)
  .slice(0, MAX_ANCHORS);
const mode = ref<Mode>(fromUrl.length ? "dossiers" : "keywords");
const chosenIds = ref<string[]>(fromUrl);
const input = ref("");
const tooShort = computed(() => input.value.trim().length > 0 && input.value.trim().length < MIN_QUERY_LENGTH);

watch(chosenIds, (ids) => router.replace({ query: ids.length ? { dossiers: ids.join(",") } : {} }));

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

      <p v-if="tooShort" class="fr-text--sm">Saisissez au moins {{ MIN_QUERY_LENGTH }} caractères.</p>
      <p v-if="status === 'idle'" class="fr-text--sm">Saisissez des mots-clés puis lancez la recherche.</p>
      <p v-else-if="status === 'loading'" class="fr-text--sm" role="status">Recherche en cours…</p>
      <div v-else-if="status === 'error'" class="fr-alert fr-alert--error fr-alert--sm" role="alert">
        <p>{{ error }}</p>
        <DsfrButton label="Réessayer" size="sm" secondary @click="retry" />
      </div>
      <p v-else-if="result && !result.dossiers.length" class="fr-text--sm" role="status">
        Aucun dossier accessible ne correspond à « {{ result.query }} ».
      </p>
      <template v-else-if="result">
        <p class="fr-text--sm" role="status">
          {{ total }} dossier(s) trouvé(s)<template v-if="total > result.dossiers.length">
            , les {{ result.dossiers.length }} plus pertinents affichés</template>, {{ result.items.length }} point(s) commun(s).
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
