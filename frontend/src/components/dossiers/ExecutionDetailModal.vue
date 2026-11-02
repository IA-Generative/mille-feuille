<script setup lang="ts">
/**
 * Le détail de l'exécution d'une réponse de l'assistant : ce qu'il a décidé, les outils appelés avec leurs arguments et
 * leurs résultats, et ce qui s'est écarté du cas normal. Pour comprendre une réponse (vide, hors sujet, lente).
 */
import { computed } from "vue";

import type { MessageExecution } from "@/types/conversation";

const props = defineProps<{ execution: MessageExecution | null }>();
const opened = defineModel<boolean>("opened", { default: false });

const MODES: Record<string, string> = {
  direct: "Réponse directe, sans consulter le dossier",
  search: "Recherche dans le dossier",
  act: "Action avec les outils",
  agent: "Réponse d'un agent de l'analyse",
  clarify: "Question de précision",
  assistant: "Renvoi vers l'assistant de l'application",
  resume: "Reprise après une décision",
};

const TOOLS: Record<string, string> = {
  search_documents: "Recherche dans le dossier",
  read_page: "Lecture d'une page",
  view_classifications: "Classifications du dossier",
  view_entities: "Entités du dossier",
  add_note: "Ajout d'une note",
  propose_update: "Proposition de modification de l'analyse",
  ask_user: "Question à la personne",
};

function duration(ms: number | null): string {
  if (ms === null) return "—";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} s`;
}

function toolLabel(name: string): string {
  return TOOLS[name] ?? name;
}

const mode = computed(() => (props.execution?.mode ? (MODES[props.execution.mode] ?? props.execution.mode) : "—"));

const summary = computed(() => {
  const execution = props.execution;
  if (!execution) return [];
  return [
    { label: "Traitement", value: mode.value },
    { label: "Modèle", value: execution.model ?? "—" },
    { label: "Durée", value: duration(execution.durationMs) },
    ...(execution.iterations !== null ? [{ label: "Tours du modèle", value: String(execution.iterations) }] : []),
  ];
});

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}
</script>

<template>
  <DsfrModal :opened="opened" title="Détail de l'exécution" size="lg" @close="opened = false">
    <template v-if="execution">
      <dl class="execution-detail__summary">
        <div v-for="item in summary" :key="item.label">
          <dt>{{ item.label }}</dt>
          <dd>{{ item.value }}</dd>
        </div>
      </dl>

      <ul v-if="execution.notes.length" class="execution-detail__notes">
        <li v-for="note in execution.notes" :key="note" class="fr-text--sm">
          <VIcon name="ri-information-line" scale="0.9" />
          {{ note }}
        </li>
      </ul>

      <h3 class="fr-h6 execution-detail__title">Outils appelés</h3>
      <p v-if="execution.steps.length === 0" class="fr-text--sm execution-detail__empty">
        Aucun outil : le modèle a répondu directement.
      </p>
      <ol v-else class="execution-detail__steps">
        <li v-for="(step, index) in execution.steps" :key="index" class="execution-detail__step">
          <details>
            <summary class="execution-detail__step-summary">
              <span class="execution-detail__step-name">{{ toolLabel(step.toolName) }}</span>
              <span v-if="step.agent" class="fr-badge fr-badge--sm fr-badge--blue-ecume">{{ step.agent }}</span>
              <span class="execution-detail__step-time fr-text--xs">
                à {{ duration(step.atMs) }} · {{ duration(step.durationMs) }}
              </span>
            </summary>
            <p class="fr-text--xs execution-detail__label">Arguments</p>
            <pre class="execution-detail__code">{{ pretty(step.arguments) }}</pre>
            <p class="fr-text--xs execution-detail__label">Résultat</p>
            <pre v-if="step.result" class="execution-detail__code">{{ step.result }}</pre>
            <p v-else class="fr-text--sm execution-detail__empty">Pas de résultat enregistré.</p>
          </details>
        </li>
      </ol>
      <p v-if="execution.omittedSteps > 0" class="fr-text--sm execution-detail__empty">
        {{ execution.omittedSteps }} appel(s) de plus ne sont pas affichés.
      </p>
    </template>
  </DsfrModal>
</template>

<style scoped>
.execution-detail__summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 0.75rem 1.5rem;
  margin: 0 0 1.5rem;
}

.execution-detail__summary dt {
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.execution-detail__summary dd {
  margin: 0;
  padding: 0;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.execution-detail__notes {
  list-style: none;
  margin: 0 0 1.5rem;
  padding: 0.75rem 1rem;
  border-radius: 0.75rem;
  background: var(--background-alt-grey);
}

.execution-detail__notes li {
  margin: 0;
  padding: 0;
  list-style: none;
}

.execution-detail__title {
  margin: 0 0 0.75rem;
}

.execution-detail__empty {
  margin: 0;
  color: var(--text-mention-grey);
}

.execution-detail__steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.execution-detail__step {
  list-style: none;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
  padding: 0.625rem 0.875rem;
}

.execution-detail__step-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  cursor: pointer;
}

.execution-detail__step-name {
  font-weight: 600;
}

.execution-detail__step-time {
  margin-left: auto;
  color: var(--text-mention-grey);
}

.execution-detail__label {
  margin: 0.75rem 0 0.25rem;
  color: var(--text-mention-grey);
}

.execution-detail__code {
  margin: 0;
  padding: 0.625rem 0.75rem;
  max-height: 14rem;
  overflow: auto;
  border-radius: 0.5rem;
  background: var(--background-alt-grey);
  font-size: 0.8125rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
