<script setup lang="ts">
// Historique d'un dossier (issue #171) : la chronologie du journal d'événements (#169), filtrable par type et par
// auteur, paginée. Le journal ne garde ni le contenu du dossier ni le nom des fichiers déposés.
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import EventFilters from "@/components/history/EventFilters.vue";
import EventTimeline from "@/components/history/EventTimeline.vue";
import BackLink from "@/components/BackLink.vue";
import { useDossierEvents } from "@/composables/useDossierEvents";
import { useDossiers } from "@/composables/useDossiers";
import { EVENT_CATEGORIES, type EventCategory } from "@/types/dossierEvent";

const route = useRoute();
const dossierId = String(route.params.id);
const { events, actors, total, pageCount, loading, error, fetchEvents, fetchActors } = useDossierEvents(dossierId);
const { list: dossiers, fetchDossier } = useDossiers();
const dossier = computed(() => dossiers.value.find((d) => d.id === dossierId));

const PAGE_SIZE = 20;
const page = ref(1);
// Les consultations sont très nombreuses : masquées par défaut.
const categories = ref<EventCategory[]>(EVENT_CATEGORIES.filter((c) => c.value !== "consultation").map((c) => c.value));
const actor = ref("");

/** Types à demander au serveur : aucun (= tous) quand toutes les catégories sont actives. */
const types = computed(() =>
  categories.value.length === EVENT_CATEGORIES.length
    ? undefined
    : EVENT_CATEGORIES.filter((c) => categories.value.includes(c.value)).flatMap((c) => c.types),
);

const load = () => fetchEvents(page.value, PAGE_SIZE, { types: types.value, actorId: actor.value || undefined });

onMounted(() => {
  void fetchDossier(dossierId).catch(() => undefined);
  void fetchActors();
  void load();
});

watch([categories, actor], () => {
  page.value = 1;
  void load();
});
watch(page, load);

// DsfrPagination travaille avec un index de page commençant à 0.
const pageIndex = computed({
  get: () => page.value - 1,
  set: (index: number) => (page.value = index + 1),
});
const pages = computed(() => Array.from({ length: pageCount.value }, (_, i) => ({ label: String(i + 1), title: `Page ${i + 1}` })));

const documentName = (documentId: string) => dossier.value?.documents.find((d) => d.id === documentId)?.name;
const noCategory = computed(() => categories.value.length === 0);
</script>

<template>
  <div class="history">
    <BackLink :to="`/dossiers/${dossierId}`">
      Retour au dossier
    </BackLink>

    <header class="history__header">
      <h1 class="fr-h2">Historique</h1>
      <p v-if="dossier" class="history__dossier">{{ dossier.name }}</p>
    </header>

    <EventFilters v-model:categories="categories" v-model:actor="actor" :actors="actors" :total="total" />

    <p v-if="loading && events.length === 0" class="history__state" role="status">
      <VIcon name="ri-loader-4-line" class="history__spinner" /> Chargement de l'historique…
    </p>
    <div v-else-if="error" class="fr-alert fr-alert--error" role="alert">
      <p>{{ error }}</p>
      <button type="button" class="fr-btn fr-btn--sm fr-btn--secondary fr-mt-1w" @click="load">Réessayer</button>
    </div>
    <p v-else-if="noCategory" class="history__state">Activez au moins un type d'événement pour afficher l'historique.</p>
    <p v-else-if="events.length === 0" class="history__state">Aucun événement ne correspond à ces critères.</p>
    <template v-else>
      <EventTimeline :events="events" :document-name="documentName" />
      <DsfrPagination v-if="pageCount > 1" v-model:current-page="pageIndex" :pages="pages" />
    </template>
  </div>
</template>

<style scoped>
.history {
  max-width: 48rem;
}

.history__header {
  margin: 0.5rem 0 1.5rem;
}

.history__header h1 {
  margin-bottom: 0.25rem;
}

.history__dossier {
  margin: 0;
  color: var(--text-mention-grey);
}

.history__state {
  color: var(--text-mention-grey);
}

.history__spinner {
  animation: history-spin 1s linear infinite;
}

@keyframes history-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
