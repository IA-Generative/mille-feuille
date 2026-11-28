<script setup lang="ts">
/** Filtres, graphe, détail et dossiers non accessibles : commun à la recherche et à l'exploration depuis des dossiers. */
import { computed, ref, watch } from "vue";

import HiddenLinksNotice from "@/components/crossSearch/HiddenLinksNotice.vue";
import LinkFilters from "@/components/crossSearch/LinkFilters.vue";
import LinkGraph from "@/components/crossSearch/LinkGraph.vue";
import SelectionPanel from "@/components/crossSearch/SelectionPanel.vue";
import { SHARED_KINDS, type CrossSearchResult, type Selection, type SharedKind } from "@/types/crossSearch";
import { buildLinkGraph, restrictToKinds } from "@/utils/linkGraph";

const props = defineProps<{ result: CrossSearchResult }>();

const kinds = ref<SharedKind[]>(SHARED_KINDS.map((k) => k.value));
const selection = ref<Selection | null>(null);

/** Seuls les types de liens trouvés se filtrent. */
const present = computed(() => [...new Set(props.result.items.map((item) => item.kind))]);
/** Le graphe, la liste et le détail montrent la même chose. */
const shown = computed(() => restrictToKinds(props.result, kinds.value));
const graph = computed(() => buildLinkGraph(shown.value, kinds.value));
// Un filtre ou un nouveau résultat peut faire disparaître ce qui était sélectionné.
watch([kinds, () => props.result], () => (selection.value = null));
</script>

<template>
  <LinkFilters v-model="kinds" :present="present" class="fr-mb-1w" />
  <p class="fr-text--xs fr-mb-2w">Cliquez sur un nœud pour voir ce qui lui est lié, sur un trait pour savoir pourquoi.</p>

  <div class="link-explorer__columns">
    <div class="link-explorer__card">
      <LinkGraph :data="graph" :selection="selection" @select="selection = $event" />
    </div>
    <div class="link-explorer__side">
      <SelectionPanel v-if="selection" :result="shown" :selection="selection" @select="selection = $event" />
      <slot v-else :result="shown" :select="(next: Selection) => (selection = next)" />
    </div>
  </div>

  <HiddenLinksNotice :links="result.hidden" class="fr-mt-2w" />
</template>

<style scoped>
.link-explorer__columns {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(16rem, 1fr);
  gap: 1rem;
  align-items: start;
}

.link-explorer__card {
  overflow: hidden;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
}

.link-explorer__side {
  max-height: 38rem;
  overflow-y: auto;
}

@media (max-width: 62em) {
  .link-explorer__columns {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
