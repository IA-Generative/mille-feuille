<script setup lang="ts">
/** À côté du graphe : l'explication et le résumé du thème, ou le détail d'un de ses groupes. */
import { computed } from "vue";

import ResemblanceCard from "@/components/crossSearch/ResemblanceCard.vue";
import { summarize, type ResemblanceTheme } from "@/components/crossSearch/resemblanceThemes";
import type { Resemblance } from "@/types/crossSearch";

const props = defineProps<{
  theme: ResemblanceTheme;
  groups: Resemblance[];
  dossierThemes: Record<string, string | null>;
  groupId: string | null;
}>();
const emit = defineEmits<{ group: [id: string | null] }>();

const group = computed(() => props.groups.find((g) => g.id === props.groupId));
const summary = computed(() => summarize(props.groups, (id) => props.dossierThemes[id] ?? null));
</script>

<template>
  <section class="cluster-summary" aria-live="polite">
    <template v-if="group">
      <button type="button" class="fr-link fr-text--sm" @click="emit('group', null)">← {{ theme.label }}</button>
      <ResemblanceCard :group="group" />
    </template>

    <template v-else>
      <h2 class="fr-h6 fr-mb-0">{{ theme.label }}</h2>
      <p class="fr-text--sm fr-mb-0">{{ theme.explanation }}</p>
      <p class="cluster-summary__box">{{ summary.sentence }}</p>
      <template v-if="groups.length">
        <p class="fr-text--xs fr-mb-0">
          Certitude : {{ summary.certainties.join(", ") }}. Thèmes de dossiers : {{ summary.dossierThemes.join(", ") }}.
        </p>
        <button v-for="entry in groups" :key="entry.id" type="button" class="detail__row" @click="emit('group', entry.id)">
          <span>{{ entry.label }}</span>
          <span class="detail__hint">{{ entry.dossierIds.length }} dossiers</span>
        </button>
      </template>
    </template>
  </section>
</template>

<style scoped src="./detail.css"></style>
<style scoped>
.cluster-summary {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
}

.cluster-summary__box {
  margin: 0;
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  background: var(--background-alt-grey);
  font-size: 0.875rem;
}
</style>
