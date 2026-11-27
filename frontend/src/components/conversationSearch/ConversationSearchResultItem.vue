<script setup lang="ts">
import { computed } from "vue";
import { RouterLink } from "vue-router";

import { formatRelativeTime } from "@/utils/dates";
import type { ConversationSearchResult } from "@/types/conversation";

const props = defineProps<{ result: ConversationSearchResult }>();

const author = computed(() => (props.result.match?.role === "assistant" ? "Assistant" : "Vous"));
const others = computed(() => props.result.matchCount - 1);
// Le message à montrer à l'ouverture ; rien quand seul le nom du dossier correspond.
const target = computed(() => ({
  path: `/dossiers/${props.result.dossierId}`,
  query: props.result.match ? { message: props.result.match.messageId } : {},
}));
</script>

<template>
  <RouterLink :to="target" class="search-result">
    <span class="search-result__head">
      <span class="search-result__dossier">{{ result.dossierName }}</span>
      <span class="search-result__date">{{ formatRelativeTime(result.date) }}</span>
    </span>
    <span v-if="result.match" class="search-result__excerpt">
      <span class="search-result__author">{{ author }} : </span>
      <template v-for="(segment, index) in result.match.excerpt" :key="index">
        <mark v-if="segment.highlighted">{{ segment.text }}</mark>
        <template v-else>{{ segment.text }}</template>
      </template>
    </span>
    <span v-else class="search-result__note">Trouvé dans le nom du dossier</span>
    <span v-if="others > 0" class="search-result__note">
      et {{ others }} autre{{ others > 1 ? "s" : "" }} message{{ others > 1 ? "s" : "" }}
    </span>
  </RouterLink>
</template>

<style scoped>
.search-result {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  background-image: none;
  color: var(--text-default-grey);
  font-size: 0.8125rem;
}

.search-result:hover {
  background-color: var(--background-alt-grey-hover);
}

.search-result__head {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.search-result__dossier {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.875rem;
  font-weight: 600;
}

.search-result__date,
.search-result__note {
  flex-shrink: 0;
  font-size: 0.6875rem;
  color: var(--text-mention-grey);
}

.search-result__excerpt {
  display: -webkit-box;
  overflow: hidden;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
}

.search-result__author {
  color: var(--text-mention-grey);
}

/* Le gras s'ajoute à la couleur : elle n'est pas le seul signal. */
.search-result mark {
  background: var(--background-action-low-blue-france);
  color: inherit;
  font-weight: 700;
}
</style>
