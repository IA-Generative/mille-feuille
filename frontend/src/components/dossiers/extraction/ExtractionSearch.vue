<script setup lang="ts">
defineProps<{
  names: { name: string; count: number }[];
  selected: string[];
  filtering: boolean;
  matchingPages: { index: number; pageNumber: number; count: number }[];
  currentIndex: number;
}>();
const query = defineModel<string>("query", { required: true });
const emit = defineEmits<{ toggle: [name: string]; goto: [index: number]; reset: [] }>();
</script>

<template>
  <div class="extraction-search">
    <div role="search">
      <label class="fr-sr-only" for="extraction-search-input">Rechercher une entité ou une valeur</label>
      <input
        id="extraction-search-input"
        v-model="query"
        class="fr-input"
        type="search"
        placeholder="Rechercher une entité ou une valeur"
      />
    </div>

    <div class="extraction-search__chips" role="group" aria-label="Filtrer par entité">
      <button
        v-for="entity in names"
        :key="entity.name"
        type="button"
        class="fr-tag"
        :aria-pressed="selected.includes(entity.name)"
        @click="emit('toggle', entity.name)"
      >
        {{ entity.name }} <small>{{ entity.count }}</small>
      </button>
      <button v-if="filtering" type="button" class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" @click="emit('reset')">
        Effacer
      </button>
    </div>

    <p v-if="filtering" class="fr-text--sm extraction-search__hits" aria-live="polite">
      <template v-if="matchingPages.length">
        {{ matchingPages.length }} {{ matchingPages.length > 1 ? "pages" : "page" }} :
        <button
          v-for="page in matchingPages"
          :key="page.index"
          type="button"
          class="extraction-search__page"
          :aria-current="page.index === currentIndex ? 'page' : undefined"
          @click="emit('goto', page.index)"
        >
          {{ page.pageNumber }} <small>({{ page.count }})</small>
        </button>
      </template>
      <template v-else>Aucun résultat.</template>
    </p>
  </div>
</template>

<style scoped>
.extraction-search {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.extraction-search__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.extraction-search__chips small {
  margin-left: 0.25rem;
  opacity: 0.7;
}

.extraction-search__hits {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.5rem;
  align-items: center;
  color: var(--text-mention-grey);
}

.extraction-search__page {
  background: none;
  border: 1px solid var(--border-default-grey);
  border-radius: 1rem;
  padding: 0 0.6rem;
  cursor: pointer;
  color: var(--text-action-high-blue-france);
}

.extraction-search__page[aria-current="page"] {
  background: var(--background-action-high-blue-france);
  border-color: var(--background-action-high-blue-france);
  color: #fff;
}
</style>
