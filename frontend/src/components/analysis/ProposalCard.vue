<script setup lang="ts">
/**
 * Proposition de modification de l'analyse de dossier : valeur actuelle →
 * valeur proposée, motif et source, avec accepter / modifier / rejeter.
 * Partagée entre la vue de l'analyse (#116) et le chat du dossier (#115).
 * Ne décide jamais seule : l'utilisateur doit cliquer.
 */
import { computed, ref } from "vue";

import {
  PROPOSAL_STATUS_LABELS,
  VERSION_SOURCE_LABELS,
  textToValue,
  valueToText,
  type ElementValue,
  type Proposal,
} from "@/types/dossierAnalysis";
import { diffWords } from "@/utils/textDiff";

const props = defineProps<{
  proposal: Proposal;
  /** Texte de la version retenue de l'élément visé (absent pour une création). */
  currentText?: string | null;
  /** Nom de l'élément visé, quand la proposition n'en porte pas. */
  elementName?: string | null;
  disabled?: boolean;
  /** Message d'erreur de la dernière action (ex : élément modifié entre-temps). */
  error?: string | null;
}>();

const emit = defineEmits<{
  accept: [];
  modify: [value: ElementValue, reason: string];
  reject: [reason: string];
}>();

const proposedText = computed(() => valueToText(props.proposal.kind, props.proposal.proposedValue));
const isCreation = computed(() => props.proposal.elementId === null);
const title = computed(() => props.proposal.definitionName ?? props.elementName ?? "Élément");
// Une relation ne s'édite pas en texte : seulement accepter ou rejeter.
const canModify = computed(() => textToValue(props.proposal.kind, "") !== null);
const diff = computed(() => (props.currentText != null ? diffWords(props.currentText, proposedText.value) : []));

type Mode = "view" | "modify" | "reject";
const mode = ref<Mode>("view");
const draft = ref("");
const note = ref("");

function startModify() {
  draft.value = proposedText.value;
  note.value = "";
  mode.value = "modify";
}

function startReject() {
  note.value = "";
  mode.value = "reject";
}

function cancel() {
  mode.value = "view";
}

function confirmModify() {
  const value = textToValue(props.proposal.kind, draft.value.trim());
  if (!value || !draft.value.trim()) return;
  emit("modify", value, note.value.trim());
  mode.value = "view";
}

function confirmReject() {
  emit("reject", note.value.trim());
  mode.value = "view";
}

const sourceLabel = computed(() =>
  props.proposal.sourceType ? (VERSION_SOURCE_LABELS[props.proposal.sourceType] ?? props.proposal.sourceType) : null,
);
</script>

<template>
  <article class="proposal-card" :aria-label="`Proposition pour ${title}`">
    <header class="proposal-card__header">
      <VIcon name="ri-lightbulb-line" />
      <strong class="proposal-card__title">{{ title }}</strong>
      <DsfrBadge :label="isCreation ? 'Nouvel élément' : 'Modification'" type="info" small />
    </header>

    <div class="proposal-card__change">
      <template v-if="isCreation">
        <p class="proposal-card__value proposal-card__value--added">{{ proposedText }}</p>
      </template>
      <template v-else>
        <p class="proposal-card__label">Valeur actuelle → valeur proposée</p>
        <p class="proposal-card__value">
          <template v-for="(part, index) in diff" :key="index">
            <del v-if="part.kind === 'removed'" class="proposal-card__removed">{{ part.text }}</del>
            <ins v-else-if="part.kind === 'added'" class="proposal-card__added">{{ part.text }}</ins>
            <span v-else>{{ part.text }}</span>
          </template>
        </p>
      </template>
    </div>

    <p class="proposal-card__reason">
      <span class="proposal-card__label">Motif :</span> {{ proposal.reason }}
      <span v-if="sourceLabel" class="proposal-card__source">(source : {{ sourceLabel }})</span>
    </p>

    <DsfrAlert v-if="error" alert type="error" small :description="error" />

    <div v-if="proposal.status !== 'pending'" class="proposal-card__decided">
      <DsfrBadge
        :label="PROPOSAL_STATUS_LABELS[proposal.status]"
        :type="proposal.status === 'rejected' ? 'warning' : 'success'"
        small
      />
    </div>

    <div v-else-if="mode === 'modify'" class="proposal-card__form">
      <label class="proposal-card__label" :for="`modify-${proposal.id}`">Valeur à appliquer</label>
      <textarea :id="`modify-${proposal.id}`" v-model="draft" class="fr-input" rows="3" />
      <label class="proposal-card__label" :for="`modify-note-${proposal.id}`">Commentaire (facultatif)</label>
      <input :id="`modify-note-${proposal.id}`" v-model="note" class="fr-input" type="text" />
      <div class="proposal-card__actions">
        <DsfrButton label="Appliquer cette valeur" small :disabled="!draft.trim()" @click="confirmModify" />
        <DsfrButton label="Annuler" small secondary @click="cancel" />
      </div>
    </div>

    <div v-else-if="mode === 'reject'" class="proposal-card__form">
      <label class="proposal-card__label" :for="`reject-${proposal.id}`">Raison du refus (facultatif)</label>
      <input :id="`reject-${proposal.id}`" v-model="note" class="fr-input" type="text" />
      <div class="proposal-card__actions">
        <DsfrButton label="Confirmer le refus" small @click="confirmReject" />
        <DsfrButton label="Annuler" small secondary @click="cancel" />
      </div>
    </div>

    <div v-else class="proposal-card__actions">
      <DsfrButton label="Accepter" small :disabled="disabled" @click="emit('accept')" />
      <DsfrButton v-if="canModify" label="Modifier" small secondary :disabled="disabled" @click="startModify" />
      <DsfrButton label="Rejeter" small tertiary :disabled="disabled" @click="startReject" />
    </div>
  </article>
</template>

<style scoped>
.proposal-card {
  border: 1px solid var(--border-default-grey);
  border-left: 4px solid var(--border-action-high-blue-france);
  border-radius: 0.5rem;
  background: var(--background-default-grey);
  padding: 0.75rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.proposal-card__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.proposal-card__title {
  flex: 1;
}

.proposal-card__label {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.proposal-card__value {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.proposal-card__removed {
  background: var(--background-contrast-error, #fddede);
  color: var(--text-default-error, #8a1c1c);
  text-decoration: line-through;
}

.proposal-card__added {
  background: var(--background-contrast-success, #c8f0d2);
  color: var(--text-default-success, #1f6b3a);
  text-decoration: none;
}

.proposal-card__value--added {
  background: var(--background-contrast-success, #c8f0d2);
  color: var(--text-default-success, #1f6b3a);
  padding: 0 0.25rem;
}

.proposal-card__reason {
  margin: 0;
  font-size: 0.875rem;
}

.proposal-card__source {
  color: var(--text-mention-grey);
}

.proposal-card__form {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.proposal-card__actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
</style>
