<script setup lang="ts">
/**
 * Modal listant les tutoriels disponibles.
 *
 * Affiche une barre latérale avec la liste des tutoriels (regroupés par
 * catégorie) et un indicateur de progression. Au clic sur un tutoriel,
 * le contenu Markdown est chargé et affiché dans le panneau principal.
 */
import { computed } from "vue";

import InfoModal from "@/components/InfoModal.vue";
import { useTutorials } from "@/composables/useTutorials";

defineProps<{
  open: boolean;
}>();

const emit = defineEmits<{
  close: [];
}>();

const {
  tutorials,
  currentSlug,
  currentHtml,
  loading,
  error,
  progress,
  progressPercent,
  isSeen,
  resetProgress,
  open: openTutorial,
} = useTutorials();

// Regroupe les tutoriels par catégorie pour l'affichage.
const groupedTutorials = computed(() => {
  const groups: Record<string, typeof tutorials.value> = {};
  for (const t of tutorials.value) {
    if (!groups[t.category]) groups[t.category] = [];
    groups[t.category].push(t);
  }
  return groups;
});

const currentTutorial = computed(() =>
  tutorials.value.find((t) => t.slug === currentSlug.value),
);
</script>

<template>
  <InfoModal title="Tutoriels" :open="open" @close="emit('close')">
    <div class="tutorials">
      <!-- Barre latérale : liste des tutoriels -->
      <aside class="tutorials__sidebar">
        <div class="tutorials__progress">
          <div class="tutorials__progress-header">
            <span class="tutorials__progress-label">Progression</span>
            <span class="tutorials__progress-count">{{ progress.seen }}/{{ progress.total }}</span>
          </div>
          <div class="tutorials__progress-bar">
            <div class="tutorials__progress-fill" :style="{ width: progressPercent + '%' }" />
          </div>
          <button
            v-if="progress.seen > 0"
            type="button"
            class="tutorials__reset"
            @click="resetProgress"
          >
            Réinitialiser
          </button>
        </div>

        <nav class="tutorials__nav">
          <template v-for="(items, category) in groupedTutorials" :key="category">
            <p class="tutorials__category">{{ category }}</p>
            <button
              v-for="t in items"
              :key="t.slug"
              type="button"
              class="tutorials__item"
              :class="{ 'tutorials__item--active': t.slug === currentSlug }"
              @click="openTutorial(t.slug)"
            >
              <VIcon :name="t.icon" class="tutorials__item-icon" />
              <span class="tutorials__item-title">{{ t.title }}</span>
              <VIcon
                v-if="isSeen(t.slug)"
                name="ri-check-line"
                class="tutorials__item-check"
              />
            </button>
          </template>
        </nav>
      </aside>

      <!-- Panneau principal : contenu du tutoriel -->
      <div class="tutorials__content">
        <template v-if="currentTutorial">
          <div class="tutorials__content-header">
            <VIcon :name="currentTutorial.icon" class="tutorials__content-icon" />
            <h3 class="tutorials__content-title">{{ currentTutorial.title }}</h3>
          </div>
          <div v-if="loading" class="tutorials__loading">Chargement…</div>
          <DsfrAlert v-else-if="error" alert type="error" small :description="error" />
          <!-- eslint-disable-next-line vue/no-v-html -- contenu statique rendu par renderMarkdown (échappé) -->
          <div v-else class="markdown tutorials__markdown" v-html="currentHtml" />
        </template>
        <div v-else class="tutorials__empty">
          <VIcon name="ri-book-open-line" class="tutorials__empty-icon" />
          <p class="tutorials__empty-text">
            Sélectionnez un tutoriel dans la liste pour commencer.
          </p>
        </div>
      </div>
    </div>
  </InfoModal>
</template>

<style scoped>
.tutorials {
  display: flex;
  height: 100%;
  gap: 0;
}

/* ── Barre latérale ────────────────────────────────────── */
.tutorials__sidebar {
  flex-shrink: 0;
  width: 16rem;
  border-right: 1px solid var(--border-default-grey);
  overflow-y: auto;
  padding: 1rem 0.5rem;
}

.tutorials__progress {
  padding: 0 0.5rem 1rem;
  border-bottom: 1px solid var(--border-default-grey);
  margin-bottom: 0.75rem;
}

.tutorials__progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.375rem;
}

.tutorials__progress-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-mention-grey);
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.tutorials__progress-count {
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.tutorials__progress-bar {
  height: 0.375rem;
  border-radius: 0.1875rem;
  background: var(--background-alt-grey);
  overflow: hidden;
}

.tutorials__progress-fill {
  height: 100%;
  border-radius: 0.1875rem;
  background: var(--background-action-high-blue-france);
  transition: width 0.3s ease;
}

.tutorials__reset {
  margin-top: 0.5rem;
  border: none;
  background: none;
  color: var(--text-mention-grey);
  font-size: 0.75rem;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}

.tutorials__reset:hover {
  color: var(--text-default-grey);
}

/* ── Navigation ───────────────────────────────────────── */
.tutorials__category {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--text-mention-grey);
  text-transform: uppercase;
  letter-spacing: 0.025em;
  padding: 0.5rem 0.5rem 0.25rem;
  margin: 0;
}

.tutorials__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  text-align: left;
  padding: 0.5rem 0.625rem;
  border: none;
  border-radius: 0.25rem;
  background: transparent;
  color: var(--text-default-grey);
  cursor: pointer;
  font-size: 0.8125rem;
  font-family: inherit;
  transition: background-color 0.15s ease;
}

.tutorials__item:hover {
  background: var(--background-alt-grey-hover);
}

.tutorials__item--active {
  background: var(--background-action-low-blue-france);
  color: var(--text-action-high-blue-france);
  font-weight: 500;
}

.tutorials__item-icon {
  flex-shrink: 0;
  font-size: 1.125rem;
}

.tutorials__item-title {
  flex: 1;
  line-height: 1.3;
}

.tutorials__item-check {
  flex-shrink: 0;
  font-size: 1rem;
  color: var(--text-action-high-blue-france);
}

/* ── Panneau de contenu ───────────────────────────────── */
.tutorials__content {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
  min-width: 0;
}

.tutorials__content-header {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  margin-bottom: 1.25rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border-default-grey);
}

.tutorials__content-icon {
  font-size: 1.5rem;
  color: var(--text-action-high-blue-france);
}

.tutorials__content-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-title-grey);
  margin: 0;
}

.tutorials__loading {
  padding: 2rem;
  text-align: center;
  color: var(--text-mention-grey);
}

.tutorials__markdown {
  font-size: 0.9375rem;
  line-height: 1.6;
  color: var(--text-default-grey);
}

/* ── État vide ────────────────────────────────────────── */
.tutorials__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 1rem;
  color: var(--text-mention-grey);
}

.tutorials__empty-icon {
  font-size: 3rem;
  opacity: 0.4;
}

.tutorials__empty-text {
  font-size: 0.9375rem;
  margin: 0;
}

/* ── Responsive ───────────────────────────────────────── */
@media (max-width: 640px) {
  .tutorials {
    flex-direction: column;
  }

  .tutorials__sidebar {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid var(--border-default-grey);
    max-height: 12rem;
  }
}
</style>
