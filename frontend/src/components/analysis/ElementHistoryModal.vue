<script setup lang="ts">
/**
 * Historique d'un élément de l'analyse de dossier : toutes ses versions, ce
 * qui a changé de l'une à l'autre (mot à mot) et la restauration d'une
 * version antérieure. Restaurer ajoute une version, ne supprime rien.
 */
import { computed, ref, watch } from "vue";

import AppModal from "@/components/AppModal.vue";
import {
  VERSION_ORIGIN_LABELS,
  VERSION_SOURCE_LABELS,
  valueToText,
  type AnalysisElement,
  type ElementVersion,
} from "@/types/dossierAnalysis";
import { diffWords } from "@/utils/textDiff";

const props = defineProps<{
  element: AnalysisElement | null;
  versions: ElementVersion[];
  loading?: boolean;
  /** Restauration possible (analyse courante et non figée). */
  canRestore: boolean;
  resolveElement?: (id: string) => string | undefined;
}>();

const emit = defineEmits<{
  close: [];
  restore: [versionId: string];
}>();

// On affiche la plus récente d'abord ; chaque version est comparée à la précédente.
const ordered = computed(() => [...props.versions].reverse());
const retainedId = computed(() => props.element?.retainedVersion?.id ?? null);
const selectedId = ref<string | null>(null);

watch(
  () => props.versions,
  (versions) => {
    selectedId.value = versions.length > 0 ? versions[versions.length - 1].id : null;
  },
);

const selected = computed(() => props.versions.find((v) => v.id === selectedId.value) ?? null);
const previous = computed(() => {
  const index = props.versions.findIndex((v) => v.id === selectedId.value);
  return index > 0 ? props.versions[index - 1] : null;
});

function text(version: ElementVersion): string {
  return props.element ? valueToText(props.element.kind, version.value, props.resolveElement) : "";
}

const diff = computed(() => {
  if (!selected.value) return [];
  return diffWords(previous.value ? text(previous.value) : "", text(selected.value));
});

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function describe(version: ElementVersion): string {
  const parts = [VERSION_ORIGIN_LABELS[version.origin]];
  if (version.authorId && version.origin === "instructor") parts.push(`par ${version.authorId}`);
  return parts.join(" ");
}
</script>

<template>
  <AppModal
    :opened="!!element"
    :title="`Historique : ${element?.definitionName ?? 'élément'}`"
    @close="emit('close')"
  >
    <p v-if="loading">Chargement…</p>
    <div v-else-if="element" class="history">
      <ol class="history__list" aria-label="Versions">
        <li v-for="version in ordered" :key="version.id">
          <button
            type="button"
            class="history__item"
            :class="{ 'history__item--selected': version.id === selectedId }"
            @click="selectedId = version.id"
          >
            <span class="history__number">v{{ version.versionNumber }}</span>
            <span class="history__meta">
              {{ describe(version) }} · {{ formatDate(version.createdAt) }}
              <DsfrBadge v-if="version.id === retainedId" label="Retenue" type="success" small />
              <DsfrBadge v-if="version.restoredFromVersionId" label="Restauration" type="info" small />
            </span>
          </button>
        </li>
      </ol>

      <section v-if="selected" class="history__detail" aria-label="Détail de la version">
        <h3 class="fr-h6">Version {{ selected.versionNumber }}</h3>
        <p class="history__label">
          {{ previous ? `Changements depuis la version ${previous.versionNumber}` : "Première version" }}
        </p>
        <p class="history__diff">
          <template v-for="(part, index) in diff" :key="index">
            <del v-if="part.kind === 'removed'" class="history__removed">{{ part.text }}</del>
            <ins v-else-if="part.kind === 'added'" class="history__added">{{ part.text }}</ins>
            <span v-else>{{ part.text }}</span>
          </template>
        </p>
        <p v-if="selected.reason" class="history__reason">
          <span class="history__label">Motif :</span> {{ selected.reason }}
          <span v-if="selected.sourceType" class="history__label">
            (source : {{ VERSION_SOURCE_LABELS[selected.sourceType] ?? selected.sourceType }})
          </span>
        </p>
        <p v-if="selected.confidence != null" class="history__label">
          Confiance : {{ Math.round(selected.confidence * 100) }} %
        </p>
        <DsfrButton
          v-if="canRestore && selected.id !== retainedId"
          label="Restaurer cette version"
          small
          secondary
          @click="emit('restore', selected.id)"
        />
      </section>
    </div>
  </AppModal>
</template>

<style scoped>
.history {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.history__list,
.history__list li {
  list-style: none;
}

.history__list {
  list-style: none;
  margin: 0;
  padding: 0;
  padding-inline-start: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 14rem;
  flex: 1;
}

.history__list li::marker {
  content: "";
}

.history__item {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
  width: 100%;
  text-align: left;
  padding: 0.5rem;
  border: 1px solid transparent;
  border-radius: 0.375rem;
  background: none;
  cursor: pointer;
}

.history__item--selected {
  border-color: var(--border-action-high-blue-france);
  background: var(--background-alt-blue-france);
}

.history__number {
  font-weight: 700;
}

.history__meta {
  font-size: 0.875rem;
  display: flex;
  gap: 0.375rem;
  flex-wrap: wrap;
  align-items: center;
}

.history__detail {
  flex: 2;
  min-width: 16rem;
}

.history__label {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.history__diff {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.history__removed {
  background: var(--background-contrast-error, #fddede);
  color: var(--text-default-error, #8a1c1c);
  text-decoration: line-through;
}

.history__added {
  background: var(--background-contrast-success, #c8f0d2);
  color: var(--text-default-success, #1f6b3a);
  text-decoration: none;
}
</style>
