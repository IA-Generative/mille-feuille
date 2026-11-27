<script setup lang="ts">
/** Un groupe de dossiers qui se ressemblent : pourquoi, avec quelle certitude, et les preuves à la demande. */
import { computed } from "vue";

import OccurrenceQuote from "@/components/crossSearch/OccurrenceQuote.vue";
import { mockDossiersByIds } from "@/composables/useCrossSearch";
import { CERTAINTIES, type Resemblance } from "@/types/crossSearch";

const props = defineProps<{ group: Resemblance }>();
const emit = defineEmits<{ explore: [ids: string[]] }>();

const dossiers = computed(() => mockDossiersByIds(props.group.dossierIds));
const proofsOf = (dossierId: string) => props.group.occurrences.filter((o) => o.dossierId === dossierId);
/** Des dossiers de thèmes différents reliés : souvent le rapprochement le plus instructif. */
const themes = computed(() => new Set(dossiers.value.map((d) => d.themeName)));
</script>

<template>
  <article class="resemblance">
    <header class="resemblance__header">
      <h3 class="fr-h6 fr-mb-0">{{ group.label }}</h3>
      <span class="fr-badge fr-badge--sm" :class="CERTAINTIES[group.certainty].badge">{{ CERTAINTIES[group.certainty].label }}</span>
    </header>
    <p class="fr-text--sm fr-mb-0">{{ group.reason }}</p>
    <p v-if="group.caution" class="resemblance__caution">{{ group.caution }}</p>

    <ul class="resemblance__dossiers">
      <li v-for="dossier in dossiers" :key="dossier.id">
        {{ dossier.name }}
        <span class="resemblance__meta">{{ dossier.reference }} · {{ dossier.themeName ?? "Sans thème" }}</span>
      </li>
    </ul>
    <p v-if="themes.size > 1" class="fr-text--xs fr-mb-0">Présent dans {{ themes.size }} thèmes différents.</p>

    <details v-if="group.occurrences.length">
      <summary class="fr-text--sm">Voir les preuves</summary>
      <template v-for="dossier in dossiers" :key="dossier.id">
        <p class="resemblance__meta fr-mt-1w fr-mb-1v">{{ dossier.reference }}</p>
        <OccurrenceQuote v-for="(proof, index) in proofsOf(dossier.id)" :key="index" :excerpt="proof" />
      </template>
    </details>

    <button type="button" class="fr-btn fr-btn--sm fr-btn--secondary resemblance__action" @click="emit('explore', group.dossierIds)">
      Explorer ces dossiers
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

.resemblance__caution {
  margin: 0;
  color: var(--text-mention-grey);
  font-size: 0.8125rem;
}

.resemblance__dossiers {
  margin: 0;
  font-size: 0.875rem;
}

.resemblance__meta {
  color: var(--text-mention-grey);
  font-size: 0.75rem;
}

.resemblance__action {
  margin-top: auto;
}
</style>
