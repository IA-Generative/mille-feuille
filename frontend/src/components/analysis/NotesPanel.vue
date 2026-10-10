<script setup lang="ts">
/**
 * Notes internes d'un dossier (issue #117) : l'instructeur consigne ses
 * observations. Elles sont **internes** (jamais visibles de l'usager),
 * **versionnées** (modifier ou restaurer ajoute une version) et servent de
 * contexte au chat du dossier. Sur demande, une note peut être analysée pour
 * **proposer** des mises à jour de l'analyse : rien n'est appliqué, les
 * propositions apparaissent dans la liste des propositions en attente.
 */
import { computed, onMounted, ref, watch } from "vue";

import PaginationBar from "@/components/PaginationBar.vue";
import { useDossierNotes } from "@/composables/useDossierNotes";
import { usePageSize } from "@/composables/usePageSize";
import type { DossierNote, NoteVersion } from "@/types/dossierNote";

const props = defineProps<{
  dossierId: string;
  /** Proposer des mises à jour suppose une analyse modifiable (courante et non figée). */
  canPropose: boolean;
}>();

const emit = defineEmits<{
  /** L'analyse d'une note est terminée : les propositions ont peut-être changé. */
  analysisFinished: [note: DossierNote];
}>();

const {
  notes,
  includeArchived,
  isLoading,
  error,
  load,
  setIncludeArchived,
  create,
  update,
  fetchVersions,
  restore,
  setArchived,
  requestProposals,
} = useDossierNotes(props.dossierId, (note) => emit("analysisFinished", note));

onMounted(() => load());

const actionError = ref<string | undefined>(undefined);
const busy = ref(false);

async function run(action: () => Promise<unknown>): Promise<boolean> {
  actionError.value = undefined;
  busy.value = true;
  try {
    await action();
    return true;
  } catch (e) {
    actionError.value = e instanceof Error ? e.message : "L'action a échoué";
    return false;
  } finally {
    busy.value = false;
  }
}

// --- Ajouter ---

const newContent = ref("");

async function submitNew() {
  const content = newContent.value.trim();
  if (!content) return;
  if (await run(() => create(content))) newContent.value = "";
}

// --- Modifier ---

const editingId = ref<string | null>(null);
const editContent = ref("");

function startEdit(note: DossierNote) {
  editingId.value = note.id;
  editContent.value = note.content;
}

async function submitEdit(note: DossierNote) {
  const content = editContent.value.trim();
  if (!content) return;
  if (content === note.content) {
    editingId.value = null;
    return;
  }
  if (await run(() => update(note.id, content))) editingId.value = null;
}

// --- Historique ---

const historyNote = ref<DossierNote | null>(null);
const historyVersions = ref<NoteVersion[]>([]);
const historyLoading = ref(false);

async function openHistory(note: DossierNote) {
  historyNote.value = note;
  historyVersions.value = [];
  historyLoading.value = true;
  try {
    historyVersions.value = (await fetchVersions(note.id)).reverse();
  } finally {
    historyLoading.value = false;
  }
}

async function onRestore(version: NoteVersion) {
  const note = historyNote.value;
  if (!note) return;
  if (await run(() => restore(note.id, version.id))) historyNote.value = null;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

// --- Analyse d'une note ---

const analysisMessage = (note: DossierNote): string | null => {
  if (note.analysisStatus === "en_cours") return "Analyse de la note en cours…";
  if (note.analysisStatus === "échec") return `L'analyse a échoué : ${note.analysisError ?? "erreur inconnue"}`;
  if (note.analysisStatus === "terminé") {
    const count = note.analysisProposalCount ?? 0;
    const outdated =
      note.analysisVersionNumber != null && note.analysisVersionNumber !== note.versionNumber
        ? ` (version ${note.analysisVersionNumber} de la note)`
        : "";
    return count > 0
      ? `${count} proposition${count > 1 ? "s" : ""} ajoutée${count > 1 ? "s" : ""} aux propositions en attente${outdated}.`
      : `Aucune mise à jour proposée${outdated}.`;
  }
  return null;
};

const hasNotes = computed(() => notes.value.length > 0);

// Pagination : taille commune à toutes les listes ; on revient à la dernière page si elle disparaît (archivage...).
const pageSize = usePageSize();
const pageIndex = ref(0);
const lastPage = computed(() => Math.max(0, Math.ceil(notes.value.length / pageSize.value) - 1));
watch(lastPage, (last) => {
  if (pageIndex.value > last) pageIndex.value = last;
});
const pagedNotes = computed(() => {
  const start = Math.min(pageIndex.value, lastPage.value) * pageSize.value;
  return notes.value.slice(start, start + pageSize.value);
});
</script>

<template>
  <section class="notes" aria-labelledby="notes-title">
    <h2 id="notes-title" class="fr-h5">Notes internes</h2>
    <p class="notes__hint">
      <VIcon name="ri-lock-line" />
      Internes : jamais visibles de l'usager. Le chat du dossier s'en sert comme contexte. Elles ne modifient
      l'analyse que si vous demandez des propositions, que vous confirmez ensuite.
    </p>

    <DsfrAlert v-if="error" type="error" :title="error" />
    <DsfrAlert v-if="actionError" type="error" :title="actionError" />

    <form class="notes__new" @submit.prevent="submitNew">
      <label class="notes__label" for="new-note">Nouvelle note</label>
      <textarea
        id="new-note"
        v-model="newContent"
        class="fr-input"
        rows="3"
        placeholder="Ex : pièce d'identité vérifiée par téléphone le …"
      />
      <div class="notes__actions">
        <DsfrButton label="Ajouter la note" small type="submit" :disabled="busy || !newContent.trim()" />
      </div>
    </form>

    <p v-if="isLoading">Chargement des notes…</p>
    <p v-else-if="!hasNotes" class="notes__empty">Aucune note pour l'instant.</p>

    <ul v-else class="notes__list">
      <li v-for="note in pagedNotes" :key="note.id" class="note" :class="{ 'note--archived': note.archived }">
        <div class="note__head">
          <span class="note__meta">
            {{ note.lastAuthorId }} · {{ formatDate(note.updatedAt) }} · version {{ note.versionNumber }}
          </span>
          <DsfrBadge v-if="note.archived" label="Archivée" type="warning" small />
          <span class="note__spacer" />
          <DsfrButton label="Historique" icon="ri-history-line" small tertiary @click="openHistory(note)" />
          <template v-if="!note.archived">
            <DsfrButton label="Modifier" icon="ri-edit-line" small secondary :disabled="busy" @click="startEdit(note)" />
            <DsfrButton
              label="Archiver"
              icon="ri-archive-line"
              small
              tertiary
              :disabled="busy"
              @click="run(() => setArchived(note.id, true))"
            />
          </template>
          <DsfrButton
            v-else
            label="Désarchiver"
            small
            secondary
            :disabled="busy"
            @click="run(() => setArchived(note.id, false))"
          />
        </div>

        <form v-if="editingId === note.id" class="note__form" @submit.prevent="submitEdit(note)">
          <label class="notes__label" :for="`edit-${note.id}`">Contenu de la note</label>
          <textarea :id="`edit-${note.id}`" v-model="editContent" class="fr-input" rows="4" required />
          <div class="notes__actions">
            <DsfrButton label="Enregistrer (nouvelle version)" small type="submit" :disabled="busy" />
            <DsfrButton label="Annuler" small secondary type="button" @click="editingId = null" />
          </div>
        </form>
        <p v-else class="note__content">{{ note.content }}</p>

        <div v-if="!note.archived" class="note__propose">
          <DsfrButton
            label="Proposer des mises à jour de l'analyse"
            icon="ri-lightbulb-line"
            small
            secondary
            :disabled="busy || !canPropose || note.analysisStatus === 'en_cours'"
            :title="
              canPropose
                ? 'Analyse cette note et ajoute des propositions en attente ; rien n\'est appliqué'
                : 'L\'analyse n\'est pas modifiable (exécution précédente ou analyse figée)'
            "
            @click="run(() => requestProposals(note.id))"
          />
          <p v-if="analysisMessage(note)" class="note__analysis" role="status">{{ analysisMessage(note) }}</p>
        </div>
      </li>
    </ul>
    <PaginationBar v-if="hasNotes" v-model:page-index="pageIndex" v-model:page-size="pageSize" :total="notes.length" />

    <label class="notes__archived-toggle">
      <input
        type="checkbox"
        :checked="includeArchived"
        @change="setIncludeArchived(($event.target as HTMLInputElement).checked)"
      />
      Afficher les notes archivées
    </label>

    <DsfrModal :opened="!!historyNote" title="Historique de la note" @close="historyNote = null">
      <p v-if="historyLoading">Chargement…</p>
      <ol v-else class="history" aria-label="Versions de la note">
        <li v-for="version in historyVersions" :key="version.id" class="history__item">
          <div class="history__head">
            <strong>Version {{ version.versionNumber }}</strong>
            <span class="note__meta">{{ version.authorId }} · {{ formatDate(version.createdAt) }}</span>
            <DsfrBadge v-if="version.restoredFromVersionId" label="Restauration" type="info" small />
            <DsfrBadge v-if="version.versionNumber === historyNote?.versionNumber" label="Actuelle" type="success" small />
            <span class="note__spacer" />
            <DsfrButton
              v-if="version.versionNumber !== historyNote?.versionNumber && !historyNote?.archived"
              label="Restaurer"
              small
              secondary
              :disabled="busy"
              @click="onRestore(version)"
            />
          </div>
          <p class="note__content">{{ version.content }}</p>
        </li>
      </ol>
    </DsfrModal>
  </section>
</template>

<style scoped>
.notes {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.notes h2 {
  margin: 0;
}

.notes__hint,
.notes__empty {
  margin: 0;
  color: var(--text-mention-grey);
  font-size: 0.875rem;
}

.notes__label,
.note__meta {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.notes__new,
.note__form {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.notes__actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.notes__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.note {
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  background: var(--background-default-grey);
}

.note--archived {
  opacity: 0.7;
}

.note__head,
.history__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.note__spacer {
  flex: 1;
}

.note__content {
  margin: 0.5rem 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.note__propose {
  margin-top: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.note__analysis {
  margin: 0;
  font-size: 0.875rem;
}

.notes__archived-toggle {
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.history,
.history li {
  list-style: none;
}

.history li::marker {
  content: "";
}

.history {
  margin: 0;
  padding: 0;
  padding-inline-start: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.history__item {
  border-bottom: 1px solid var(--border-default-grey);
  padding-bottom: 0.5rem;
}
</style>
