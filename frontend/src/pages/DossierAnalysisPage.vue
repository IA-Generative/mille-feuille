<script setup lang="ts">
/**
 * Analyse de dossier (issue #116, parent #106) : le document de travail d'un
 * dossier, une analyse par exécution. L'instructeur y voit chaque élément
 * avec sa provenance (modèle / instructeur / reprise), son historique, peut
 * apporter une valeur, restaurer une version antérieure et traiter les
 * propositions en attente. Interne : jamais montré aux usagers.
 */
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import ElementHistoryModal from "@/components/analysis/ElementHistoryModal.vue";
import NotesPanel from "@/components/analysis/NotesPanel.vue";
import ProposalCard from "@/components/analysis/ProposalCard.vue";
import MarkdownText from "@/components/MarkdownText.vue";
import PaginationBar from "@/components/PaginationBar.vue";
import { useAnalysisLive, type PresenceEntry } from "@/composables/useAnalysisLive";
import { useDossierAnalysis } from "@/composables/useDossierAnalysis";
import { useDossiers } from "@/composables/useDossiers";
import { usePageSize } from "@/composables/usePageSize";
import {
  ELEMENT_KIND_LABELS,
  VERSION_ORIGIN_LABELS,
  textToValue,
  valueToText,
  type AnalysisElement,
  type AnalysisElementKind,
  type ElementVersion,
} from "@/types/dossierAnalysis";

const route = useRoute();
const dossierId = String(route.params.id);

const { list: dossiers, fetchDossier } = useDossiers();
const dossier = computed(() => dossiers.value.find((d) => d.id === dossierId));

const {
  analyses,
  analysis,
  proposals,
  isLoading,
  error,
  isCurrent,
  isFrozen,
  canEdit,
  load,
  select,
  refresh,
  fetchVersions,
  addVersion,
  restoreVersion,
  createElement,
  acceptProposal,
  modifyProposal,
  rejectProposal,
} = useDossierAnalysis(dossierId);

onMounted(async () => {
  await Promise.all([load(), fetchDossier(dossierId).catch(() => undefined)]);
});

// Travail à plusieurs (#118) : présence des autres instructeurs et verrou court par
// élément, seulement sur l'analyse courante et modifiable.
const liveAnalysisId = computed(() => (analysis.value && canEdit.value ? analysis.value.id : undefined));
const {
  others: otherInstructors,
  othersByElement,
  lockedByOthers,
  sync: syncLive,
  setFocus,
  acquireLock,
  releaseLock,
  touchActivity,
} = useAnalysisLive(dossierId, liveAnalysisId);
watch(liveAnalysisId, (id) => syncLive(id), { immediate: true });

const presenceLabel = (entry: PresenceEntry) =>
  `${entry.displayName} ${entry.mode === "editing" ? "modifie" : "consulte"}`;
const lockLabel = (elementId: string) => {
  const lock = lockedByOthers.value.get(elementId);
  return lock ? `Verrouillé par ${lock.lockedByName ?? lock.lockedBy}` : "";
};

const KIND_ORDER: AnalysisElementKind[] = ["classification", "entity", "relation", "synthesis", "field"];

const groups = computed(() =>
  KIND_ORDER.map((kind) => ({
    kind,
    label: ELEMENT_KIND_LABELS[kind],
    elements: (analysis.value?.elements ?? []).filter((e) => e.kind === kind),
  })).filter((group) => group.elements.length > 0),
);

// Pagination par groupe (classifications, entités...) : une page courante par type, une taille commune.
const pageSize = usePageSize();
const pageByKind = ref<Partial<Record<AnalysisElementKind, number>>>({});

function pageOf(group: { kind: AnalysisElementKind; elements: AnalysisElement[] }): number {
  const last = Math.max(0, Math.ceil(group.elements.length / pageSize.value) - 1);
  return Math.min(pageByKind.value[group.kind] ?? 0, last);
}

function setPage(kind: AnalysisElementKind, index: number) {
  pageByKind.value = { ...pageByKind.value, [kind]: index };
}

function visibleElements(group: { kind: AnalysisElementKind; elements: AnalysisElement[] }): AnalysisElement[] {
  const start = pageOf(group) * pageSize.value;
  return group.elements.slice(start, start + pageSize.value);
}

const elementNames = computed(() => {
  const names = new Map<string, string>();
  for (const element of analysis.value?.elements ?? []) {
    const text = element.retainedVersion ? valueToText(element.kind, element.retainedVersion.value) : "";
    names.set(element.id, element.definitionName ? `${element.definitionName} (${text})` : text);
  }
  return names;
});
const resolveElement = (id: string) => elementNames.value.get(id);

function elementText(element: AnalysisElement): string {
  return element.retainedVersion
    ? valueToText(element.kind, element.retainedVersion.value, resolveElement)
    : "";
}

function currentTextFor(elementId: string | null): string | null {
  if (!elementId) return null;
  const element = analysis.value?.elements.find((e) => e.id === elementId);
  return element ? elementText(element) : null;
}

function elementNameFor(elementId: string | null): string | null {
  if (!elementId) return null;
  return analysis.value?.elements.find((e) => e.id === elementId)?.definitionName ?? null;
}

function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "";
}

function provenance(element: AnalysisElement): string {
  const version = element.retainedVersion;
  if (!version) return "";
  const label = VERSION_ORIGIN_LABELS[version.origin];
  return version.origin === "instructor" && version.authorId ? `${label} (${version.authorId})` : label;
}

const originBadgeType = (version: ElementVersion | null) =>
  version?.origin === "instructor" ? "success" : version?.origin === "carried_over" ? "new" : "info";

// --- Actions : la plupart passent par un message d'erreur commun ---

const actionError = ref<string | undefined>(undefined);
const busy = ref(false);

async function run(action: () => Promise<unknown>) {
  actionError.value = undefined;
  busy.value = true;
  try {
    await action();
  } catch (e) {
    actionError.value = e instanceof Error ? e.message : "L'action a échoué";
  } finally {
    busy.value = false;
  }
}

// --- Apporter une valeur ---

const editingId = ref<string | null>(null);
const editText = ref("");
const editReason = ref("");

const isEditable = (element: AnalysisElement) => textToValue(element.kind, "") !== null;

async function startEdit(element: AnalysisElement) {
  actionError.value = undefined;
  // On prend le verrou avant d'ouvrir le formulaire : si un autre instructeur modifie
  // déjà cet élément, le message dit qui, et on n'ouvre rien.
  const lock = await acquireLock(element.id);
  if (!lock.ok) {
    actionError.value = lock.message;
    return;
  }
  editingId.value = element.id;
  editText.value = elementText(element);
  editReason.value = "";
}

async function cancelEdit() {
  editingId.value = null;
  await releaseLock();
}

async function submitEdit(element: AnalysisElement) {
  const value = textToValue(element.kind, editText.value.trim());
  if (!value || !editText.value.trim() || !editReason.value.trim()) return;
  await run(() => addVersion(element.id, value, editReason.value.trim(), element.retainedVersion?.id));
  if (!actionError.value) {
    editingId.value = null;
    await releaseLock(); // déjà libéré par le serveur après l'enregistrement
  }
}

// --- Historique ---

const historyElement = ref<AnalysisElement | null>(null);
const historyVersions = ref<ElementVersion[]>([]);
const historyLoading = ref(false);

async function openHistory(element: AnalysisElement) {
  historyElement.value = element;
  setFocus(element.id, "viewing");
  historyVersions.value = [];
  historyLoading.value = true;
  try {
    historyVersions.value = await fetchVersions(element.id);
  } finally {
    historyLoading.value = false;
  }
}

async function onRestore(versionId: string) {
  const element = historyElement.value;
  if (!element) return;
  await run(() => restoreVersion(element.id, versionId));
  if (!actionError.value) historyElement.value = null;
}

// --- Ajouter un élément à la main ---

const newKind = ref<AnalysisElementKind>("entity");
const newName = ref("");
const newText = ref("");
const newReason = ref("");
const addableKinds: AnalysisElementKind[] = ["entity", "classification", "synthesis", "field"];

async function submitNew() {
  const value = textToValue(newKind.value, newText.value.trim());
  if (!value || !newText.value.trim()) return;
  await run(() => createElement(newKind.value, value, newName.value.trim(), newReason.value.trim()));
  if (!actionError.value) {
    newName.value = "";
    newText.value = "";
    newReason.value = "";
  }
}

const statusLabel: Record<string, string> = { brouillon: "Brouillon", validée: "Validée", figée: "Figée" };
</script>

<template>
  <div class="analysis-page">
    <RouterLink :to="`/dossiers/${dossierId}`" class="fr-link fr-icon-arrow-left-line fr-link--icon-left">
      Retour au dossier
    </RouterLink>

    <header class="analysis-page__header">
      <h1 class="fr-h3">Analyse du dossier{{ dossier ? ` « ${dossier.name} »` : "" }}</h1>
      <div v-if="analysis" class="analysis-page__meta">
        <DsfrBadge :label="statusLabel[analysis.status]" :type="isFrozen ? 'warning' : 'info'" small />
        <span>Exécution n° {{ analysis.sequence }}</span>
        <span v-if="analysis.analyseVersion">· analyse {{ analysis.analyseVersion }}</span>
        <span v-if="analysis.startedAt">· lancée le {{ formatDate(analysis.startedAt) }}</span>
        <span v-if="otherInstructors.length > 0" class="analysis-page__others" role="status">
          <VIcon name="ri-group-line" />
          Aussi sur cette analyse : {{ otherInstructors.map((entry) => entry.displayName).join(", ") }}
        </span>
        <label v-if="analyses.length > 1" class="analysis-page__select">
          <span class="fr-sr-only">Exécution à consulter</span>
          <select class="fr-select" :value="analysis.id" @change="select(($event.target as HTMLSelectElement).value)">
            <option v-for="(item, index) in analyses" :key="item.id" :value="item.id">
              Exécution n° {{ item.sequence }}{{ index === 0 ? " (actuelle)" : "" }}
            </option>
          </select>
        </label>
      </div>
    </header>

    <DsfrAlert v-if="error" type="error" :title="error" />
    <p v-else-if="isLoading">Chargement de l'analyse…</p>

    <DsfrAlert
      v-else-if="!analysis"
      type="info"
      title="Aucune analyse pour ce dossier"
      description="L'analyse du dossier est créée à chaque lancement du dossier."
      small
    />

    <template v-else>
      <DsfrAlert
        v-if="!isCurrent"
        type="info"
        title="Exécution précédente"
        description="Vous consultez une exécution plus ancienne : elle est en lecture seule."
        small
      />
      <DsfrAlert
        v-else-if="isFrozen"
        type="warning"
        title="Analyse figée"
        description="Cette analyse ne peut plus être modifiée."
        small
      />
      <DsfrAlert v-if="actionError" type="error" :title="actionError" />

      <section v-if="proposals.length > 0" class="analysis-page__section" aria-labelledby="proposals-title">
        <h2 id="proposals-title" class="fr-h5">Propositions en attente ({{ proposals.length }})</h2>
        <p class="analysis-page__hint">
          Rien n'est appliqué tant que vous n'avez pas accepté, modifié ou rejeté la proposition.
        </p>
        <div class="analysis-page__proposals">
          <ProposalCard
            v-for="proposal in proposals"
            :key="proposal.id"
            :proposal="proposal"
            :current-text="currentTextFor(proposal.elementId)"
            :element-name="elementNameFor(proposal.elementId)"
            :disabled="busy || !canEdit"
            @accept="run(() => acceptProposal(proposal.id))"
            @modify="(value, reason) => run(() => modifyProposal(proposal.id, value, reason))"
            @reject="(reason) => run(() => rejectProposal(proposal.id, reason))"
          />
        </div>
      </section>

      <p v-if="groups.length === 0" class="analysis-page__empty">
        Aucun élément pour l'instant : ils apparaissent au fil de l'exécution du dossier.
      </p>

      <section
        v-for="group in groups"
        :key="group.kind"
        class="analysis-page__section"
        :aria-labelledby="`group-${group.kind}`"
      >
        <h2 :id="`group-${group.kind}`" class="fr-h5">{{ group.label }} ({{ group.elements.length }})</h2>
        <ul class="analysis-page__elements">
          <li v-for="element in visibleElements(group)" :key="element.id" class="element">
            <div class="element__head">
              <strong class="element__name">{{ element.definitionName ?? ELEMENT_KIND_LABELS[element.kind] }}</strong>
              <DsfrBadge
                v-if="element.retainedVersion"
                :label="provenance(element)"
                :type="originBadgeType(element.retainedVersion)"
                small
              />
              <DsfrBadge
                v-if="element.originElementId && element.retainedVersion?.origin !== 'carried_over'"
                label="Reprise"
                type="new"
                small
                title="Repris de l'exécution précédente"
              />
              <DsfrBadge v-if="element.needsReview" label="À revoir" type="warning" small />
              <DsfrBadge v-if="lockedByOthers.get(element.id)" :label="lockLabel(element.id)" type="warning" small />
              <span
                v-for="entry in othersByElement.get(element.id) ?? []"
                :key="entry.userId"
                class="element__presence"
                :class="{ 'element__presence--editing': entry.mode === 'editing' }"
              >
                <VIcon :name="entry.mode === 'editing' ? 'ri-edit-line' : 'ri-eye-line'" />
                {{ presenceLabel(entry) }}
              </span>
              <span v-if="element.firstPageNumber" class="element__meta">page {{ element.firstPageNumber }}</span>
              <span v-if="element.retainedVersion?.confidence != null" class="element__meta">
                confiance {{ Math.round(element.retainedVersion.confidence * 100) }} %
              </span>
              <span class="element__spacer" />
              <DsfrButton label="Historique" icon="ri-history-line" small tertiary @click="openHistory(element)" />
              <DsfrButton
                v-if="canEdit && isEditable(element)"
                label="Modifier"
                icon="ri-edit-line"
                small
                secondary
                :disabled="busy || !!lockedByOthers.get(element.id)"
                :title="lockedByOthers.get(element.id) ? lockLabel(element.id) : 'Modifier cet élément'"
                @click="startEdit(element)"
              />
            </div>

            <MarkdownText v-if="element.kind === 'synthesis'" :content="elementText(element)" class="element__value" />
            <p v-else class="element__value">{{ elementText(element) }}</p>

            <p v-if="element.needsReview && element.reviewReason" class="element__review">
              À revoir : {{ element.reviewReason }}
            </p>
            <p
              v-if="element.retainedVersion?.origin === 'instructor' && element.latestModelVersion"
              class="element__model"
            >
              Valeur du modèle : {{ valueToText(element.kind, element.latestModelVersion.value, resolveElement) }}
            </p>

            <form v-if="editingId === element.id" class="element__form" @submit.prevent="submitEdit(element)">
              <label class="element__label" :for="`edit-${element.id}`">Nouvelle valeur</label>
              <textarea
                :id="`edit-${element.id}`"
                v-model="editText"
                class="fr-input"
                rows="3"
                required
                @input="touchActivity"
              />
              <label class="element__label" :for="`reason-${element.id}`">Motif (obligatoire)</label>
              <input
                :id="`reason-${element.id}`"
                v-model="editReason"
                class="fr-input"
                type="text"
                required
                @input="touchActivity"
              />
              <div class="element__actions">
                <DsfrButton label="Enregistrer" small type="submit" :disabled="busy" />
                <DsfrButton label="Annuler" small secondary type="button" @click="cancelEdit" />
              </div>
            </form>
          </li>
        </ul>
        <PaginationBar
          :total="group.elements.length"
          :page-index="pageOf(group)"
          v-model:page-size="pageSize"
          @update:page-index="(index) => setPage(group.kind, index)"
        />
      </section>

      <details v-if="canEdit" class="analysis-page__add">
        <summary>Ajouter un élément à la main</summary>
        <form class="element__form" @submit.prevent="submitNew">
          <label class="element__label" for="new-kind">Type</label>
          <select id="new-kind" v-model="newKind" class="fr-select">
            <option v-for="kind in addableKinds" :key="kind" :value="kind">{{ ELEMENT_KIND_LABELS[kind] }}</option>
          </select>
          <label class="element__label" for="new-name">Nom (ex : adresse)</label>
          <input id="new-name" v-model="newName" class="fr-input" type="text" />
          <label class="element__label" for="new-text">Valeur</label>
          <textarea id="new-text" v-model="newText" class="fr-input" rows="2" required />
          <label class="element__label" for="new-reason">Motif (facultatif)</label>
          <input id="new-reason" v-model="newReason" class="fr-input" type="text" />
          <div class="element__actions">
            <DsfrButton label="Ajouter" small type="submit" :disabled="busy" />
          </div>
        </form>
      </details>
    </template>

    <NotesPanel :dossier-id="dossierId" :can-propose="!!analysis && canEdit" @analysis-finished="refresh" />

    <ElementHistoryModal
      :element="historyElement"
      :versions="historyVersions"
      :loading="historyLoading"
      :can-restore="canEdit && !busy"
      :resolve-element="resolveElement"
      @close="historyElement = null"
      @restore="onRestore"
    />
  </div>
</template>

<style scoped>
.analysis-page {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.analysis-page__header h1 {
  margin: 0.5rem 0;
}

.analysis-page__meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  font-size: 0.875rem;
}

.analysis-page__others {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  color: var(--text-mention-grey);
}

.element__presence {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0 0.5rem;
  border-radius: 1rem;
  background: var(--background-alt-blue-france);
  color: var(--text-action-high-blue-france);
  font-size: 0.75rem;
}

.element__presence--editing {
  background: var(--background-contrast-warning, #fff4e0);
  color: var(--text-default-warning, #8d533e);
}

.analysis-page__select {
  margin-left: auto;
}

.analysis-page__section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.analysis-page__section h2 {
  margin: 0;
}

.analysis-page__hint,
.analysis-page__empty {
  margin: 0;
  color: var(--text-mention-grey);
  font-size: 0.875rem;
}

.analysis-page__proposals {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.analysis-page__elements {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.element {
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  background: var(--background-default-grey);
}

.element__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.element__spacer {
  flex: 1;
}

.element__meta,
.element__label,
.element__model {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.element__value {
  margin: 0.375rem 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.element__review {
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
  color: var(--text-default-warning);
}

.element__model {
  margin: 0.25rem 0 0;
}

.element__form {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-top: 0.5rem;
}

.element__actions {
  display: flex;
  gap: 0.5rem;
}

.analysis-page__add summary {
  cursor: pointer;
  font-weight: 500;
}
</style>
