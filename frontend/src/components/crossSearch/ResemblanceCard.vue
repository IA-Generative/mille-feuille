<script setup lang="ts">
/** Un groupe de dossiers qui se ressemblent : pourquoi, avec quelle certitude, et les preuves à la demande. */
import { computed } from "vue";
import { RouterLink } from "vue-router";

import OccurrenceQuote from "@/components/crossSearch/OccurrenceQuote.vue";
import { MAX_ANCHORS } from "@/composables/useCrossSearch";
import { CERTAINTIES, type Resemblance } from "@/types/crossSearch";

const props = defineProps<{ group: Resemblance }>();
const emit = defineEmits<{ explore: [ids: string[]]; dismiss: [group: Resemblance] }>();

const proofsOf = (dossierId: string) => props.group.occurrences.filter((o) => o.dossierId === dossierId);
/** Des dossiers de thèmes différents reliés : souvent le rapprochement le plus instructif. */
const themes = computed(() => new Set(props.group.dossiers.map((d) => d.themeName)));
</script>

<template>
  <article class="resemblance">
    <header class="resemblance__header">
      <h3 class="fr-h6 fr-mb-0">{{ group.label }}</h3>
      <span class="fr-badge fr-badge--sm" :class="CERTAINTIES[group.certainty].badge">{{ CERTAINTIES[group.certainty].label }}</span>
    </header>
    <p class="fr-text--sm fr-mb-0">{{ group.reason }}</p>

    <ul class="resemblance__dossiers">
      <li v-for="dossier in group.dossiers" :key="dossier.id">
        <RouterLink :to="{ name: 'dossier-detail', params: { id: dossier.id } }">{{ dossier.name }}</RouterLink>
        <span class="resemblance__meta">{{ dossier.reference }} · {{ dossier.themeName ?? "Sans thème" }}</span>
      </li>
    </ul>
    <p v-if="themes.size > 1" class="fr-text--xs fr-mb-0">Présent dans {{ themes.size }} thèmes différents.</p>

    <details v-if="group.occurrences.length">
      <summary class="fr-text--sm">Voir les preuves</summary>
      <template v-for="dossier in group.dossiers" :key="dossier.id">
        <p class="resemblance__meta fr-mt-1w fr-mb-1v">{{ dossier.reference }}</p>
        <OccurrenceQuote v-for="(proof, index) in proofsOf(dossier.id)" :key="index" :excerpt="proof" />
      </template>
    </details>

    <button type="button" class="fr-btn fr-btn--sm fr-btn--secondary" @click="emit('explore', group.dossierIds.slice(0, MAX_ANCHORS))">
      Explorer ces dossiers
    </button>
    <button type="button" class="fr-link fr-text--sm" @click="emit('dismiss', group)">
      {{ group.dismissed ? "Rétablir ce rapprochement" : "Écarter : ce rapprochement est faux" }}
    </button>
  </article>
</template>

<style scoped>
.resemblance {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 1rem 1.25rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
}

.resemblance__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  width: 100%;
}

.resemblance__dossiers {
  margin: 0;
  font-size: 0.875rem;
}

.resemblance__dossiers .resemblance__meta {
  display: block;
}

.resemblance__meta {
  color: var(--text-mention-grey);
  font-size: 0.75rem;
}
</style>
