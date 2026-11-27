<script setup lang="ts">
/** Choisit le détail à montrer selon la sélection : dossier, point commun, trait ou comparaison. */
import { computed } from "vue";

import DossierDetail from "@/components/crossSearch/DossierDetail.vue";
import LinkDetail from "@/components/crossSearch/LinkDetail.vue";
import NodeDetail from "@/components/crossSearch/NodeDetail.vue";
import PairDetail from "@/components/crossSearch/PairDetail.vue";
import type { CrossSearchResult, Selection } from "@/types/crossSearch";
import { hiddenNodeId } from "@/utils/linkGraph";

const props = defineProps<{ result: CrossSearchResult; selection: Selection }>();
const emit = defineEmits<{ select: [selection: Selection | null] }>();

const nodeId = computed(() => (props.selection.type === "node" ? props.selection.id : null));
const dossier = computed(() => props.result.dossiers.find((d) => d.id === nodeId.value));
const item = computed(() => props.result.items.find((i) => i.id === nodeId.value));
const hidden = computed(() => props.result.hidden.find((h) => hiddenNodeId(h.themeName) === nodeId.value));
</script>

<template>
  <section class="selection-panel" aria-live="polite">
    <button type="button" class="fr-link fr-text--sm selection-panel__back" @click="emit('select', null)">
      <VIcon name="ri-arrow-left-line" scale="0.9" /> Tous les résultats
    </button>

    <LinkDetail v-if="selection.type === 'link'" :result="result" :dossier-id="selection.dossierId" :target-id="selection.targetId" @select="emit('select', $event)" />
    <PairDetail v-else-if="selection.type === 'pair'" :result="result" :dossier-ids="selection.dossierIds" @select="emit('select', $event)" />
    <DossierDetail v-else-if="dossier" :result="result" :dossier="dossier" @select="emit('select', $event)" />
    <NodeDetail v-else-if="item || hidden" :result="result" :item="item" :hidden="hidden" @select="emit('select', $event)" />
  </section>
</template>

<style scoped>
.selection-panel {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.75rem;
}

.selection-panel__back {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}
</style>
