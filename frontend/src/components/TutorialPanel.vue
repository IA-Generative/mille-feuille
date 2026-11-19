<script setup lang="ts">
import { computed, ref } from "vue";

import { useDialogFocus } from "@/composables/useDialogFocus";
import { useTutorials } from "@/composables/useTutorials";

const {
  tutorials, currentSlug, steps, stepIndex, currentStep, isLastStep,
  loading, error, panelOpen, minimized, progress, isSeen,
  resetProgress, load, closePanel, toggleMinimize, leaveTutorial,
  next, prev,
} = useTutorials();

// Focus : à l'ouverture il va sur le titre ; à la fermeture il revient à l'élément qui avait le focus.
const titleRef = ref<HTMLElement | null>(null);
useDialogFocus(panelOpen, titleRef);

// Regroupe les tutoriels par catégorie pour l'affichage de la liste.
const groups = computed(() => {
  const out: Record<string, typeof tutorials.value> = {};
  for (const t of tutorials.value) (out[t.category] ??= []).push(t);
  return out;
});
const currentTutorial = computed(() => tutorials.value.find((t) => t.slug === currentSlug.value));

// Texte annoncé par le lecteur d'écran à chaque changement d'étape.
const announcement = computed(() =>
  steps.value.length > 1
    ? `Étape ${stepIndex.value + 1} sur ${steps.value.length} : ${currentStep.value?.title ?? ""}`
    : "",
);
</script>

<template>
  <section
    v-if="panelOpen"
    class="tutorial-panel"
    :class="{ 'tutorial-panel--minimized': minimized }"
    aria-labelledby="tutorial-panel-title"
    @keydown.esc="closePanel"
  >
    <header class="tutorial-panel__header">
      <h2 id="tutorial-panel-title" ref="titleRef" tabindex="-1" class="fr-h6 fr-mb-0 tutorial-panel__title">
        {{ currentTutorial?.title ?? "Tutoriels" }}
      </h2>
      <DsfrButton
        :label="minimized ? 'Rouvrir le tutoriel' : 'Réduire le tutoriel'"
        :icon="minimized ? 'ri-arrow-up-s-line' : 'ri-subtract-line'"
        icon-only tertiary no-outline size="sm"
        :aria-expanded="!minimized"
        aria-controls="tutorial-panel-body"
        @click="toggleMinimize"
      />
      <DsfrButton label="Fermer le tutoriel" icon="ri-close-line" icon-only tertiary no-outline size="sm" @click="closePanel" />
    </header>

    <p class="fr-sr-only" aria-live="polite">{{ announcement }}</p>

    <!-- v-show : réduit, le corps passe en display:none → sorti du Tab et des lecteurs d'écran -->
    <div id="tutorial-panel-body" v-show="!minimized" class="tutorial-panel__body">
      <template v-if="!currentSlug">
        <p class="fr-text--sm fr-mb-1w">{{ progress.seen }} tutoriel(s) vu(s) sur {{ progress.total }}</p>
        <DsfrButton
          v-if="progress.seen > 0"
          label="Réinitialiser la progression"
          tertiary no-outline size="sm"
          @click="resetProgress"
        />
        <nav aria-label="Liste des tutoriels">
          <template v-for="(items, category) in groups" :key="category">
            <p class="fr-text--sm fr-text--bold fr-mb-1v fr-mt-2w">{{ category }}</p>
            <ul class="fr-raw-list">
              <li v-for="t in items" :key="t.slug">
                <button
                  type="button"
                  class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm tutorial-panel__item"
                  @click="load(t.slug)"
                >
                  <VIcon :name="t.icon" aria-hidden="true" />
                  {{ t.title }}
                  <template v-if="isSeen(t.slug)">
                    <VIcon name="ri-check-line" aria-hidden="true" />
                    <span class="fr-sr-only">(déjà vu)</span>
                  </template>
                </button>
              </li>
            </ul>
          </template>
        </nav>
      </template>
      <template v-else>
        <DsfrButton
          label="Tous les tutoriels" icon="ri-arrow-left-line"
          tertiary no-outline size="sm" class="fr-mb-2w"
          @click="leaveTutorial"
        />
        <p v-if="loading" class="fr-text--sm">Chargement…</p>
        <DsfrAlert v-else-if="error" type="error" small :description="error" />
        <template v-else-if="currentStep">
          <DsfrStepper v-if="steps.length > 1" :steps="steps.map((s) => s.title)" :current-step="stepIndex + 1" />
          <!-- eslint-disable-next-line vue/no-v-html -- Markdown statique rendu par renderMarkdown (échappé) -->
          <div class="markdown fr-text--sm" v-html="currentStep.html" />
          <div class="tutorial-panel__actions">
            <DsfrButton label="Précédent" secondary size="sm" :disabled="stepIndex === 0" @click="prev" />
            <DsfrButton :label="isLastStep ? 'Terminer' : 'Suivant'" size="sm" @click="isLastStep ? leaveTutorial() : next()" />
          </div>
        </template>
      </template>
    </div>
  </section>
</template>

<style scoped>
/* Ordinateur : colonne collée à droite, DANS le flux → l'application se rétrécit, rien n'est recouvert. */
.tutorial-panel {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: 24rem;
  height: 100vh;
  position: sticky;
  top: 0;
  box-sizing: border-box;
  background: var(--background-default-grey);
  color: var(--text-default-grey);
  border-left: 1px solid var(--border-default-grey);
}
.tutorial-panel__header {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-default-grey);
}
.tutorial-panel__title { flex: 1; color: var(--text-title-grey); }
.tutorial-panel__title:focus-visible { outline: 2px solid var(--border-active-blue-france); }
.tutorial-panel__body { flex: 1; min-height: 0; overflow-y: auto; padding: 1rem; }
.tutorial-panel__item { width: 100%; justify-content: flex-start; gap: 0.5rem; }
.tutorial-panel__actions { display: flex; justify-content: space-between; gap: 0.5rem; margin-top: 1.5rem; }

/* Réduit : barre flottante hors flux, l'application reprend toute sa largeur. */
.tutorial-panel--minimized {
  position: fixed;
  top: auto; /* annule le `top: 0` du mode sticky : sinon, avec `bottom`, la barre s'étire sur toute la hauteur */
  right: 1rem;
  bottom: 1rem;
  width: 22rem;
  height: auto;
  z-index: 500; /* sous les vraies modales */
  border: 1px solid var(--border-default-grey);
  box-shadow: var(--raised-shadow);
}

/* Sous 1248 px (rupture DSFR « xl ») : volet en bas, pleine largeur. */
@media (max-width: 77.99em) {
  .tutorial-panel,
  .tutorial-panel--minimized {
    position: fixed;
    inset: auto 0 0 0;
    width: auto;
    max-height: 45vh;
    height: auto;
    z-index: 500;
    border-left: none;
    border-top: 1px solid var(--border-default-grey);
    box-shadow: var(--raised-shadow);
  }
}
</style>
