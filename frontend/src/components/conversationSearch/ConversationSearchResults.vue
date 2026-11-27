<script setup lang="ts">
import { computed } from "vue";

import ConversationSearchResultItem from "@/components/conversationSearch/ConversationSearchResultItem.vue";
import type { SearchStatus } from "@/composables/useConversationSearch";
import type { ConversationSearchResult } from "@/types/conversation";

const props = defineProps<{ results: ConversationSearchResult[]; total: number; status: SearchStatus }>();
defineEmits<{ more: []; retry: [] }>();

// Annoncé aux lecteurs d'écran à chaque changement.
const summary = computed(() => {
  if (props.status === "loading") return "Recherche…";
  if (props.status === "error") return "La recherche a échoué.";
  if (props.total === 0) return "Aucune conversation trouvée.";
  return `${props.total} conversation${props.total > 1 ? "s" : ""}`;
});
</script>

<template>
  <div class="search-results">
    <p class="search-results__summary" role="status">{{ summary }}</p>
    <nav v-if="results.length > 0" class="search-results__list" aria-label="Résultats de la recherche">
      <ConversationSearchResultItem v-for="result in results" :key="result.conversationId" :result="result" />
      <button
        v-if="status === 'ready' && results.length < total"
        type="button"
        class="search-results__action"
        @click="$emit('more')"
      >
        Afficher plus
      </button>
    </nav>
    <button v-if="status === 'error'" type="button" class="search-results__action" @click="$emit('retry')">
      Réessayer
    </button>
  </div>
</template>

<style scoped>
.search-results {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.search-results__summary {
  flex-shrink: 0;
  margin: 0 0 0.375rem;
  padding: 0 0.75rem;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.search-results__list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.125rem;
  min-height: 0;
  overflow-y: auto;
}

.search-results__action {
  flex-shrink: 0;
  padding: 0.5rem 0.75rem;
  border: none;
  border-radius: 0.5rem;
  background: transparent;
  color: var(--text-action-high-blue-france);
  font-family: inherit;
  font-size: 0.8125rem;
  cursor: pointer;
}
</style>
