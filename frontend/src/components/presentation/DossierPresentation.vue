<script setup lang="ts">
import PresentationAgents from "@/components/presentation/PresentationAgents.vue";
import PresentationDocuments from "@/components/presentation/PresentationDocuments.vue";
import PresentationEntities from "@/components/presentation/PresentationEntities.vue";
import PresentationFacts from "@/components/presentation/PresentationFacts.vue";
import PresentationPending from "@/components/presentation/PresentationPending.vue";
import PresentationSection from "@/components/presentation/PresentationSection.vue";
import PresentationSummary from "@/components/presentation/PresentationSummary.vue";
import SuggestedQuestions from "@/components/presentation/SuggestedQuestions.vue";
import type { DossierPresentation, SuggestedQuestion } from "@/types/dossierPresentation";

// La présentation d'un dossier, en tête de sa conversation : l'essentiel d'abord (nature, chiffres, résumé), le détail
// dans des blocs repliés, puis les questions dont la réponse est déjà prête. Chaque bloc est un composant séparé.
defineProps<{
  presentation: DossierPresentation;
  /** Les vues de détail existent (classification par fichier et par page, explorateur des entités). */
  detailable?: boolean;
  /** Le résumé peut être (re)généré depuis cette présentation. */
  regenerable?: boolean;
}>();
const emit = defineEmits<{
  ask: [question: SuggestedQuestion];
  detail: [kind: "label" | "entity"];
  regenerateSummary: [];
}>();
</script>

<template>
  <article class="dossier-presentation" aria-label="Présentation du dossier">
    <PresentationPending v-if="presentation.status === 'pending'" :dossier-name="presentation.dossierName" />

    <div v-else-if="presentation.status === 'failed'" class="dossier-presentation__failed" role="alert">
      <p class="dossier-presentation__failed-title">L'analyse a échoué</p>
      <p class="dossier-presentation__failed-text">{{ presentation.error }}</p>
    </div>

    <template v-else>
      <header class="dossier-presentation__header">
        <p class="dossier-presentation__eyebrow">Présentation du dossier</p>
        <h2 class="dossier-presentation__title">{{ presentation.dossierName }}</h2>
        <PresentationFacts
          :classification="presentation.classification"
          :entity-count="presentation.entities.length"
          :agent-count="presentation.agents.length"
          :document-count="presentation.documents.length"
          :detailable="detailable"
          @detail="emit('detail', 'label')"
        />
      </header>

      <PresentationSummary
        v-if="presentation.summary"
        :content="presentation.summary"
        :regenerable="regenerable && !presentation.refreshing"
        @regenerate="emit('regenerateSummary')"
      />
      <p v-else-if="regenerable && !presentation.refreshing" class="dossier-presentation__no-summary">
        <span>{{ presentation.summaryError ?? "Pas de résumé pour l'instant." }}</span>
        <button type="button" class="dossier-presentation__retry" @click="emit('regenerateSummary')">
          {{ presentation.summaryError ? "Réessayer" : "Générer le résumé" }}
        </button>
      </p>

      <div class="dossier-presentation__sections">
        <PresentationSection
          v-if="presentation.entities.length > 0"
          title="Informations clés"
          icon="ri-braces-line"
          :count="presentation.entities.length"
        >
          <PresentationEntities
            :entities="presentation.entities"
            :detailable="detailable"
            @detail="emit('detail', 'entity')"
          />
        </PresentationSection>
        <PresentationSection
          v-if="presentation.agents.length > 0"
          title="Synthèses des agents"
          icon="ri-robot-2-line"
          :count="presentation.agents.length"
        >
          <PresentationAgents :agents="presentation.agents" />
        </PresentationSection>
        <PresentationSection
          v-if="presentation.documents.length > 0"
          title="Documents"
          icon="ri-folder-2-line"
          :count="presentation.documents.length"
        >
          <PresentationDocuments :documents="presentation.documents" />
        </PresentationSection>
      </div>

      <SuggestedQuestions :questions="presentation.suggestions" @ask="emit('ask', $event)" />
    </template>
  </article>
</template>

<style scoped>
.dossier-presentation {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.5rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 1.5rem;
  background: var(--background-default-grey);
}

.dossier-presentation__header {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.dossier-presentation__eyebrow {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-mention-grey);
}

.dossier-presentation__title {
  margin: 0;
  font-size: 1.375rem;
}

.dossier-presentation__sections {
  margin-top: 0.25rem;
}

.dossier-presentation__sections > :last-child {
  border-bottom: 1px solid var(--border-default-grey);
}

.dossier-presentation__no-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.25rem 1rem;
  margin: 0;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}

.dossier-presentation__retry {
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  color: var(--text-action-high-blue-france);
  cursor: pointer;
}

.dossier-presentation__retry:hover {
  text-decoration: underline;
}

.dossier-presentation__failed-title {
  margin: 0 0 0.25rem;
  font-weight: 600;
}

.dossier-presentation__failed-text {
  margin: 0;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}
</style>
