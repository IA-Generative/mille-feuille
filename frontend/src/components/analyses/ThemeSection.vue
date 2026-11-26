<script setup lang="ts">
import { computed, ref, watch } from "vue";

import AnalyseCard from "@/components/analyses/AnalyseCard.vue";
import PagerNav from "@/components/PagerNav.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import type { AnalyseSummary } from "@/types/analyse";
import { userMessage } from "@/utils/api";

const PAGE_SIZE = 6;

const props = defineProps<{
  /** null : la section « Sans thème ». */
  themeId: string | null;
  title: string;
  description?: string;
  count: number;
  query: string;
  editable?: boolean;
}>();
const emit = defineEmits<{ edit: []; remove: [] }>();

const { fetchPage } = useAnalyses();

const isOpen = ref(true);
const page = ref(1);
const pageCount = ref(1);
const analyses = ref<AnalyseSummary[]>([]);
const error = ref("");
const tags = computed(() => (props.themeId ? [props.title] : []));
let lastRequest = 0;

async function load() {
  const request = ++lastRequest;
  try {
    const result = await fetchPage({ page: page.value, size: PAGE_SIZE, q: props.query, themeId: props.themeId });
    if (request !== lastRequest) return;
    error.value = "";
    analyses.value = result.items;
    pageCount.value = result.pages;
    // La page demandée n'existe plus (suppression) : revenir à la dernière.
    if (page.value > Math.max(1, result.pages)) page.value = Math.max(1, result.pages);
  } catch (cause) {
    if (request === lastRequest) error.value = userMessage(cause, "Les analyses n'ont pas pu être chargées.");
  }
}

watch(
  () => [props.query, props.themeId],
  () => {
    if (page.value === 1) load();
    else page.value = 1;
  },
);
watch([page, () => props.count], load);
load();
</script>

<template>
  <section class="theme-section">
    <header class="theme-section__header">
      <h2 class="theme-section__title">
        <button type="button" class="theme-section__toggle" :aria-expanded="isOpen" @click="isOpen = !isOpen">
          <VIcon :name="isOpen ? 'ri-arrow-down-s-line' : 'ri-arrow-right-s-line'" />
          {{ title }}
          <span class="theme-section__count">{{ count }}</span>
        </button>
      </h2>
      <div v-if="editable" class="theme-section__actions">
        <DsfrButton label="Modifier" tertiary no-outline size="sm" @click="emit('edit')" />
        <DsfrButton label="Supprimer" tertiary no-outline size="sm" @click="emit('remove')" />
      </div>
    </header>

    <!-- Visible même replié : elle aide à savoir quoi ouvrir. -->
    <p v-if="description" class="fr-text--sm theme-section__description">{{ description }}</p>

    <div v-if="isOpen">
      <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
      <p v-else-if="count === 0" class="fr-text--sm theme-section__empty">
        Aucune analyse. Choisissez ce thème dans la page d'une analyse pour la ranger ici.
      </p>
      <template v-else>
        <div class="theme-section__grid">
          <AnalyseCard v-for="analyse in analyses" :key="analyse.id" :analyse="analyse" :tags="tags" />
        </div>
        <PagerNav v-model:page="page" :page-count="pageCount" class="theme-section__pagination" />
      </template>
    </div>
  </section>
</template>

<style scoped>
.theme-section {
  margin-bottom: 2rem;
}

.theme-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
  border-bottom: 1px solid var(--border-default-grey);
}

.theme-section__title {
  margin: 0;
  font-size: 1.25rem;
}

.theme-section__toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0;
  font: inherit;
}

.theme-section__count {
  font-size: 0.875rem;
  font-weight: 400;
  color: var(--text-mention-grey);
}

.theme-section__description,
.theme-section__empty {
  color: var(--text-mention-grey);
}

.theme-section__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
  gap: 1rem;
}

.theme-section__pagination {
  display: flex;
  justify-content: center;
  margin-top: 1rem;
}
</style>
