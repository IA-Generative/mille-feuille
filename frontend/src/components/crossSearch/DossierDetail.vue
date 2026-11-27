<script setup lang="ts">
/** Un dossier choisi : ses points communs, les dossiers qui lui sont liés et ses extraits. */
import { computed } from "vue";

import KindDot from "@/components/crossSearch/KindDot.vue";
import OccurrenceQuote from "@/components/crossSearch/OccurrenceQuote.vue";
import type { CrossSearchResult, FoundDossier, Selection } from "@/types/crossSearch";
import { relatedDossiers } from "@/utils/linkGraph";

const props = defineProps<{ result: CrossSearchResult; dossier: FoundDossier }>();
const emit = defineEmits<{ select: [selection: Selection] }>();

const shared = computed(() => props.result.items.filter((i) => i.dossierIds.includes(props.dossier.id)));
const related = computed(() => relatedDossiers(props.result, props.dossier.id));
const hidden = computed(() => props.result.hidden.filter((h) => h.dossierIds.includes(props.dossier.id)));
</script>

<template>
  <h2 class="fr-h6 fr-mb-0">{{ dossier.name }}</h2>
  <p class="fr-text--sm fr-mb-0">{{ dossier.reference }} · {{ dossier.analyseName }}</p>

  <p v-if="!shared.length" class="fr-text--sm fr-mb-0">Aucun point commun avec les autres résultats.</p>
  <template v-else>
    <h3 class="detail__title">Points communs ({{ shared.length }})</h3>
    <button v-for="item in shared" :key="item.id" type="button" class="detail__row" @click="emit('select', { type: 'link', dossierId: dossier.id, targetId: item.id })">
      <KindDot :kind="item.kind" />
      <span>{{ item.label }}</span>
      <span class="detail__hint">Pourquoi ?</span>
    </button>

    <h3 class="detail__title">Dossiers liés ({{ related.length }})</h3>
    <button v-for="entry in related" :key="entry.dossier.id" type="button" class="detail__row detail__row--stacked" @click="emit('select', { type: 'pair', dossierIds: [dossier.id, entry.dossier.id] })">
      <span>{{ entry.dossier.name }}</span>
      <span class="detail__hint">par {{ entry.items.map((i) => i.label).join(", ") }}</span>
    </button>
  </template>

  <p v-for="link in hidden" :key="link.themeName ?? ''" class="fr-text--xs fr-mb-0">
    <VIcon name="ri-lock-line" scale="0.8" /> Lié aussi à des dossiers non accessibles ({{ link.themeName ?? "Sans thème" }}).
  </p>

  <h3 class="detail__title">Extraits</h3>
  <OccurrenceQuote v-for="(excerpt, index) in dossier.excerpts" :key="index" :excerpt="excerpt" />

  <!-- Dossier fictif : rien à ouvrir tant que la recherche n'est pas branchée. -->
  <button type="button" class="fr-btn fr-btn--sm fr-btn--secondary" disabled>Ouvrir le dossier (bientôt)</button>
</template>

<style scoped src="./detail.css"></style>
