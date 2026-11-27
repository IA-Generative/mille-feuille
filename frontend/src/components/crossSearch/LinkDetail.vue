<script setup lang="ts">
/** Un trait choisi : pourquoi ce dossier est relié à ce point commun, preuve à l'appui. */
import { computed } from "vue";

import KindDot from "@/components/crossSearch/KindDot.vue";
import OccurrenceQuote from "@/components/crossSearch/OccurrenceQuote.vue";
import { LINK_REASONS, type CrossSearchResult, type Selection } from "@/types/crossSearch";
import { hiddenNodeId } from "@/utils/linkGraph";

const props = defineProps<{ result: CrossSearchResult; dossierId: string; targetId: string }>();
const emit = defineEmits<{ select: [selection: Selection] }>();

const dossier = computed(() => props.result.dossiers.find((d) => d.id === props.dossierId));
const item = computed(() => props.result.items.find((i) => i.id === props.targetId));
const hidden = computed(() => props.result.hidden.find((h) => hiddenNodeId(h.themeName) === props.targetId));
const proofs = computed(() => item.value?.occurrences.filter((o) => o.dossierId === props.dossierId) ?? []);
const others = computed(() =>
  props.result.dossiers.filter((d) => d.id !== props.dossierId && item.value?.dossierIds.includes(d.id)),
);
</script>

<template>
  <template v-if="dossier">
    <h2 class="fr-h6 fr-mb-0">Pourquoi ce lien ?</h2>
    <p class="fr-text--sm fr-mb-0">
      <button type="button" class="fr-link fr-text--sm" @click="emit('select', { type: 'node', id: dossier.id })">{{ dossier.name }}</button>
    </p>

    <template v-if="item">
      <p class="detail__subject"><KindDot :kind="item.kind" /> {{ item.label }}</p>
      <p class="fr-text--sm fr-mb-0">{{ LINK_REASONS[item.kind].reason }}</p>
      <OccurrenceQuote v-for="(proof, index) in proofs" :key="index" :excerpt="proof" />
      <p v-if="LINK_REASONS[item.kind].caution" class="detail__caution">{{ LINK_REASONS[item.kind].caution }}</p>

      <h3 class="detail__title">Également présent dans</h3>
      <button v-for="other in others" :key="other.id" type="button" class="detail__row" @click="emit('select', { type: 'pair', dossierIds: [dossier.id, other.id] })">
        <span>{{ other.name }}</span>
        <span class="detail__hint">Comparer</span>
      </button>
    </template>

    <p v-else-if="hidden" class="fr-text--sm fr-mb-0">
      Ce dossier est lié à des dossiers non accessibles du thème « {{ hidden.themeName ?? "Sans thème" }} ». La raison du
      lien n'est pas communiquée.
    </p>
  </template>
</template>

<style scoped src="./detail.css"></style>
