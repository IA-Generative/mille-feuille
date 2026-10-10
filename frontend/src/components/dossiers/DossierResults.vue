<script setup lang="ts">
import { computed, ref } from "vue";

import DossierResultsDetail from "@/components/dossiers/DossierResultsDetail.vue";
import MarkdownText from "@/components/MarkdownText.vue";
import type { Analyse } from "@/types/analyse";
import { SUMMARY_STATUS_LABELS, type Dossier } from "@/types/dossier";

const props = defineProps<{ dossier: Dossier; analyse?: Analyse }>();

const emit = defineEmits<{
  regenerateSummary: [];
}>();

const classificationStep = computed(() => props.dossier.executionSteps.find((s) => s.kind === "classification"));
const extractionStep = computed(() => props.dossier.executionSteps.find((s) => s.kind === "extraction"));
const agentSteps = computed(() => props.dossier.executionSteps.filter((s) => s.kind === "agent" && !!s.output));

const classificationResult = computed(() => {
  const output = classificationStep.value?.output;
  if (!output) return undefined;
  const match = output.match(/^(.*) \(confiance : (\d+)%\)$/);
  if (!match) return { label: output, confidence: undefined as number | undefined };
  return { label: match[1], confidence: Number(match[2]) };
});

const extractionResult = computed(() => {
  const output = extractionStep.value?.output;
  if (!output || !output.includes(" : ")) return undefined;
  return output.split(" · ").map((pair) => {
    const [name, value] = pair.split(" : ");
    return { name, value };
  });
});

type ResultCardKind = "classification" | "extraction" | "agent" | "summary";

interface ResultCard {
  id: string;
  kind: ResultCardKind;
  icon: string;
  title: string;
  preview: string;
  pending: boolean;
}

function extractionPreview(): string {
  if (extractionResult.value) {
    const count = extractionResult.value.length;
    return `${count} ${count > 1 ? "entités" : "entité"}`;
  }
  return extractionStep.value?.output ?? "En attente";
}

function classificationPreview(): string {
  if (classificationResult.value) return classificationResult.value.label;
  return classificationStep.value?.output ?? "En attente";
}

const cards = computed<ResultCard[]>(() => {
  const items: ResultCard[] = [
    {
      id: "classification",
      kind: "classification",
      icon: "ri-price-tag-3-line",
      title: "Classification",
      pending: !classificationStep.value,
      preview: classificationPreview(),
    },
    {
      id: "extraction",
      kind: "extraction",
      icon: "ri-braces-line",
      title: "Entités",
      pending: !extractionStep.value,
      preview: extractionPreview(),
    },
  ];
  agentSteps.value.forEach((step) => {
    items.push({
      id: step.id,
      kind: "agent",
      icon: "ri-robot-line",
      title: step.label,
      pending: false,
      preview: step.output ?? "",
    });
  });
  // Carte résumé du dossier (issue #52) : affichée dès que le résumé
  // existe ou est en cours de génération.
  const summary = props.dossier.summary;
  const summaryStatus = props.dossier.summaryStatus;
  if (summaryStatus !== "en_attente" || summary) {
    items.push({
      id: "dossier-summary",
      kind: "summary",
      icon: "ri-file-text-line",
      title: "Résumé du dossier",
      pending: !summary,
      preview: summaryStatus === "en_cours"
        ? SUMMARY_STATUS_LABELS[summaryStatus]
        : summary?.content ?? "",
    });
  }
  return items;
});

const selectedCardId = ref<string | undefined>(undefined);
const isDetailOpened = ref(false);
const selectedCard = computed(() => cards.value.find((c) => c.id === selectedCardId.value));

function openDetail(card: ResultCard) {
  if (card.pending) return;
  selectedCardId.value = card.id;
  isDetailOpened.value = true;
}

const carouselRef = ref<HTMLElement | null>(null);
function scrollCarousel(direction: 1 | -1) {
  carouselRef.value?.scrollBy({ left: direction * 240, behavior: "smooth" });
}
</script>

<template>
  <div class="dossier-results">
    <button
      type="button"
      class="dossier-results__nav dossier-results__nav--prev"
      aria-label="Résultats précédents"
      @click="scrollCarousel(-1)"
    >
      <VIcon name="ri-arrow-left-s-line" />
    </button>

    <div ref="carouselRef" class="dossier-results__carousel">
      <button
        v-for="card in cards"
        :key="card.id"
        type="button"
        class="dossier-results__card"
        :class="{
          'dossier-results__card--agent': card.kind === 'agent',
          'dossier-results__card--pending': card.pending,
        }"
        :disabled="card.pending"
        @click="openDetail(card)"
      >
        <span class="dossier-results__icon" :class="{ 'dossier-results__icon--agent': card.kind === 'agent' }">
          <VIcon :name="card.icon" />
        </span>
        <span class="dossier-results__card-title">{{ card.title }}</span>
        <span class="fr-text--sm dossier-results__card-preview">{{ card.preview }}</span>
      </button>
    </div>

    <button
      type="button"
      class="dossier-results__nav dossier-results__nav--next"
      aria-label="Résultats suivants"
      @click="scrollCarousel(1)"
    >
      <VIcon name="ri-arrow-right-s-line" />
    </button>

    <DsfrModal
      v-if="selectedCard"
      :opened="isDetailOpened"
      @close="isDetailOpened = false"
      :title="selectedCard.title"
      :icon="selectedCard.icon"
    >
      <DossierResultsDetail
        v-if="selectedCard.kind === 'classification' || selectedCard.kind === 'extraction'"
        :key="selectedCard.kind"
        :dossier-id="dossier.id"
        :kind="selectedCard.kind === 'classification' ? 'label' : 'entity'"
      />

      <MarkdownText v-else-if="selectedCard.kind === 'agent'" :content="selectedCard.preview" class="dossier-results__agent-output" />

      <div v-else-if="selectedCard.kind === 'summary'">
        <div v-if="dossier.summaryStatus === 'en_cours'" class="dossier-results__summary-loading">
          <VIcon name="ri-loader-4-line" class="dossier-results__spinner" />
          <span class="fr-text--sm">Génération du résumé en cours…</span>
        </div>
        <div v-else-if="dossier.summaryStatus === 'échec'" class="dossier-results__summary-error">
          <VIcon name="ri-error-warning-line" />
          <span class="fr-text--sm">{{ dossier.summaryError ?? "Erreur lors de la génération du résumé" }}</span>
        </div>
        <MarkdownText v-else-if="dossier.summary" :content="dossier.summary.content" />
        <button
          v-if="dossier.summaryStatus !== 'en_cours'"
          type="button"
          class="fr-link fr-text--sm dossier-results__regenerate"
          @click="emit('regenerateSummary')"
        >
          <VIcon name="ri-refresh-line" />
          Régénérer le résumé
        </button>
      </div>

      <RouterLink
        v-if="selectedCard.kind !== 'agent' && selectedCard.kind !== 'summary'"
        :to="`/analyses/${dossier.analyseId}`"
        class="fr-link fr-text--sm dossier-results__config-link"
      >
        Voir la configuration
      </RouterLink>
    </DsfrModal>
  </div>
</template>

<style scoped>
.dossier-results {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
}

.dossier-results__nav {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 50%;
  background: var(--background-default-grey);
  cursor: pointer;
}

.dossier-results__nav:hover {
  background: var(--background-alt-grey-hover);
}

.dossier-results__carousel {
  flex: 1;
  display: flex;
  gap: 1rem;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  padding: 0.25rem;
}

.dossier-results__card {
  scroll-snap-align: start;
  flex: 0 0 auto;
  width: 12rem;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  background: var(--background-default-grey);
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
  padding: 1rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
  cursor: pointer;
  text-align: left;
  transition:
    box-shadow 0.15s ease,
    transform 0.15s ease;
}

.dossier-results__card:hover:not(:disabled) {
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.dossier-results__card--pending {
  cursor: default;
  opacity: 0.6;
}

.dossier-results__card--agent {
  border-left: 3px solid #5b4fd1;
}

.dossier-results__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.65rem;
  background: linear-gradient(135deg, #6a5cff1a 0%, #ff6ca01a 100%);
  color: #4b3fd9;
  flex-shrink: 0;
}

.dossier-results__icon--agent {
  background: linear-gradient(135deg, #5b4fd11a 0%, #d1477a1a 100%);
}

.dossier-results__card-title,
.dossier-results__card-preview {
  display: block;
  width: 100%;
  min-width: 0;
  overflow-wrap: anywhere;
}

.dossier-results__card-title {
  font-weight: bold;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
}

.dossier-results__card-preview {
  color: var(--text-mention-grey);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
}

.dossier-results__agent-output {
  margin: 0;
  white-space: pre-wrap;
}

.dossier-results__summary-loading,
.dossier-results__summary-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-mention-grey);
}

.dossier-results__spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.dossier-results__regenerate {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  margin-top: 1rem;
  cursor: pointer;
  background: transparent;
  border: none;
  padding: 0;
}

.dossier-results__config-link {
  display: inline-block;
  margin-top: 1rem;
}
</style>
