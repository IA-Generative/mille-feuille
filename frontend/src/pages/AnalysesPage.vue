<script setup lang="ts">
import { computed, ref, watch } from "vue";

import CreateAnalyseModal from "@/components/analyses/CreateAnalyseModal.vue";
import PagerNav from "@/components/PagerNav.vue";
import { useAnalyses } from "@/composables/useAnalyses";

const BROWSE_PAGE_SIZE = 6;
// Pas de recherche côté serveur (GET /analyses n'a pas de paramètre `q`) :
// une recherche charge une page large et filtre côté client plutôt que de
// dépendre de la pagination normale.
const SEARCH_PAGE_SIZE = 100;

const { list, pageCount: serverPageCount, fetchList } = useAnalyses();

const searchQuery = ref("");
const currentPage = ref(1);
const isCreateModalOpened = ref(false);
const isSearching = computed(() => searchQuery.value.trim().length > 0);

const filteredAnalyses = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  if (!query) return list.value;
  return list.value.filter(
    (analyse) => analyse.name.toLowerCase().includes(query) || analyse.description.toLowerCase().includes(query),
  );
});

const pageCount = computed(() =>
  isSearching.value ? Math.max(1, Math.ceil(filteredAnalyses.value.length / BROWSE_PAGE_SIZE)) : serverPageCount.value,
);

const paginatedAnalyses = computed(() => {
  if (!isSearching.value) return list.value;
  const start = (currentPage.value - 1) * BROWSE_PAGE_SIZE;
  return filteredAnalyses.value.slice(start, start + BROWSE_PAGE_SIZE);
});

watch(
  [currentPage, isSearching],
  async ([page, searching]) => {
    if (searching) await fetchList(1, SEARCH_PAGE_SIZE);
    else await fetchList(page, BROWSE_PAGE_SIZE);
  },
  { immediate: true },
);

function onSearch(query: string) {
  searchQuery.value = query;
  currentPage.value = 1;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" });
}

function onAnalyseCreated() {
  currentPage.value = 1;
}
</script>

<template>
  <div>
    <div class="analyses-page__header">
      <div>
        <h1 class="fr-h2">Analyses</h1>
        <p class="fr-text--lead">Retrouvez vos analyses ou créez-en une nouvelle.</p>
      </div>
      <DsfrButton label="Créer une analyse" icon="ri-add-line" @click="isCreateModalOpened = true" />
    </div>

    <DsfrSearchBar
      label="Rechercher une analyse"
      placeholder="Nom ou description..."
      :model-value="searchQuery"
      class="analyses-page__search"
      @update:model-value="onSearch"
      @search="onSearch"
    />

    <p v-if="paginatedAnalyses.length === 0" class="fr-text--sm">Aucune analyse ne correspond à cette recherche.</p>

    <div v-else class="analyses-page__grid">
      <DsfrCard
        v-for="analyse in paginatedAnalyses"
        :key="analyse.id"
        :title="analyse.name"
        :description="analyse.description"
        :link="{ name: 'analyse-detail', params: { id: analyse.id } }"
        :detail="formatDate(analyse.createdAt)"
        detail-icon="ri-calendar-line"
        :end-detail="`${analyse.agentCount} agent${analyse.agentCount > 1 ? 's' : ''}`"
        end-detail-icon="ri-robot-line"
      />
    </div>

    <PagerNav v-model:page="currentPage" :page-count="pageCount" class="analyses-page__pagination" />

    <CreateAnalyseModal v-model:opened="isCreateModalOpened" @created="onAnalyseCreated" />
  </div>
</template>

<style scoped>
.analyses-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.analyses-page__search {
  max-width: 32rem;
  margin: 1.5rem 0 2rem;
}

.analyses-page__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
  gap: 1.5rem;
}

/* Tronque la description des cartes à 3 lignes maximum */
.analyses-page__grid :deep(.fr-card__desc) {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.analyses-page__pagination {
  margin-top: 2rem;
  display: flex;
  justify-content: center;
}
</style>
