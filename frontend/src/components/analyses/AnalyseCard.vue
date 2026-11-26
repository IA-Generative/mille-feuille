<script setup lang="ts">
import MarkdownText from "@/components/MarkdownText.vue";
import type { AnalyseSummary } from "@/types/analyse";

/** `tags` : libellés en lecture seule (le thème aujourd'hui, d'autres plus tard). */
defineProps<{ analyse: AnalyseSummary; tags: string[] }>();

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" });
}
</script>

<template>
  <article class="analyse-card">
    <h3 class="analyse-card__title">
      <RouterLink :to="{ name: 'analyse-detail', params: { id: analyse.id } }" class="analyse-card__link">
        {{ analyse.name }}
      </RouterLink>
    </h3>
    <ul v-if="tags.length" class="analyse-card__tags" aria-label="Tags">
      <li v-for="tag in tags" :key="tag" class="fr-tag fr-tag--sm">{{ tag }}</li>
    </ul>
    <!-- Pas de <p> : le rendu markdown produit lui-même des blocs. -->
    <div class="analyse-card__desc">
      <MarkdownText :content="analyse.description" :lines="3" />
    </div>
    <p class="analyse-card__meta">
      <span><VIcon name="ri-calendar-line" scale="0.8" /> {{ formatDate(analyse.createdAt) }}</span>
      <span>
        <VIcon name="ri-robot-line" scale="0.8" />
        {{ analyse.agentCount }} agent{{ analyse.agentCount > 1 ? "s" : "" }}
      </span>
    </p>
  </article>
</template>

<style scoped>
.analyse-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1.25rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
  background: var(--background-default-grey);
}

.analyse-card:hover {
  background: var(--background-alt-grey);
}

.analyse-card__title {
  margin: 0;
  font-size: 1.125rem;
  line-height: 1.5rem;
}

/* Toute la carte ouvre l'analyse. */
.analyse-card__link {
  background: none;
}

.analyse-card__link::after {
  content: "";
  position: absolute;
  inset: 0;
}

.analyse-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.analyse-card__desc {
  flex: 1;
  font-size: 0.875rem;
  line-height: 1.5rem;
}

.analyse-card__meta {
  display: flex;
  justify-content: space-between;
  margin: 0;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}
</style>
