<script setup lang="ts">
/** Deux dossiers comparés : tout ce qui les relie, avec la preuve de chaque côté. */
import { computed } from "vue";

import KindDot from "@/components/crossSearch/KindDot.vue";
import OccurrenceQuote from "@/components/crossSearch/OccurrenceQuote.vue";
import { reasonOf, type CrossSearchResult, type Selection } from "@/types/crossSearch";
import { sharedItems } from "@/utils/linkGraph";

const props = defineProps<{ result: CrossSearchResult; dossierIds: [string, string] }>();
const emit = defineEmits<{ select: [selection: Selection] }>();

const dossiers = computed(() => props.dossierIds.map((id) => props.result.dossiers.find((d) => d.id === id)!));
const items = computed(() => sharedItems(props.result, ...props.dossierIds));
</script>

<template>
  <h2 class="fr-h6 fr-mb-0">Ce qui les relie ({{ items.length }})</h2>
  <button v-for="dossier in dossiers" :key="dossier.id" type="button" class="fr-link fr-text--sm detail__link" @click="emit('select', { type: 'node', id: dossier.id })">
    {{ dossier.name }}
  </button>

  <section v-for="item in items" :key="item.id" class="detail__block">
    <p class="detail__subject"><KindDot :kind="item.kind" /> {{ item.uncertain ? "≈ " : "" }}{{ item.label }}</p>
    <p class="fr-text--sm fr-mb-0">{{ reasonOf(item).reason }}</p>
    <template v-for="dossier in dossiers" :key="dossier.id">
      <p class="detail__hint">Dans {{ dossier.reference }}</p>
      <OccurrenceQuote v-for="(proof, index) in item.occurrences.filter((o) => o.dossierId === dossier.id)" :key="index" :excerpt="proof" />
    </template>
    <p v-if="reasonOf(item).caution" class="detail__caution">{{ reasonOf(item).caution }}</p>
  </section>
</template>

<style scoped src="./detail.css"></style>
