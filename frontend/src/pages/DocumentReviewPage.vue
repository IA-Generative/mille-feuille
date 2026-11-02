<script setup lang="ts">
/**
 * Revue d'un brouillon de document (backend issue #142, parent #107) : tous les champs du modèle, chacun avec sa
 * valeur, son statut et ses sources, que l'instructeur valide, modifie, rejette ou fait régénérer ; à droite,
 * l'aperçu fidèle du document (PDF, même moteur que le fichier final). Interne : jamais montré aux usagers.
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";

import DraftFieldCard from "@/components/documents/DraftFieldCard.vue";
import FieldHistoryModal from "@/components/documents/FieldHistoryModal.vue";
import PdfPreview from "@/components/documents/PdfPreview.vue";
import BackLink from "@/components/BackLink.vue";
import { draftErrorMessage, incompleteFieldsFrom, useDocumentDrafts } from "@/composables/useDocumentDrafts";
import type { DocumentDraft, DraftField, FieldValue, FieldVersion, GeneratedDocument } from "@/types/documentDraft";

const route = useRoute();
const dossierId = String(route.params.id);
const draftId = String(route.params.draftId);
const api = useDocumentDrafts(dossierId);

const draft = ref<DocumentDraft | null>(null);
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const info = ref("");
const generated = ref<GeneratedDocument | null>(null);

// --- Chargement et suivi de la génération par l'agent (asynchrone : on relit tant qu'elle est en cours) ---

let poll: ReturnType<typeof setInterval> | undefined;

async function reload() {
  draft.value = await api.fetchDraft(draftId);
  if (draft.value.generationStatus === "en_cours") startPolling();
  else stopPolling();
}

function startPolling() {
  if (poll) return;
  poll = setInterval(() => void reload().catch(() => undefined), 2000);
}

function stopPolling() {
  if (poll) clearInterval(poll);
  poll = undefined;
}

onMounted(async () => {
  try {
    await reload();
  } catch (e) {
    error.value = draftErrorMessage(e, "Impossible de charger ce brouillon.");
  } finally {
    loading.value = false;
  }
});
onBeforeUnmount(stopPolling);

/** Exécute une écriture, puis relit le brouillon ; l'erreur du serveur s'affiche telle quelle. */
async function run(work: () => Promise<unknown>, success = "") {
  busy.value = true;
  error.value = "";
  info.value = "";
  try {
    await work();
    await reload();
    if (success) info.value = success;
  } catch (e) {
    error.value = draftErrorMessage(e, "L'opération a échoué.");
    await reload().catch(() => undefined);
  } finally {
    busy.value = false;
  }
}

const editable = computed(() => draft.value?.status === "brouillon" && !busy.value);
const generating = computed(() => draft.value?.generationStatus === "en_cours");
const labelOf = (name: string) => draft.value?.fields.find((f) => f.name === name)?.label ?? name;

/** Obligatoire et pas encore validé : mis en évidence. */
const needsAttention = (field: DraftField) =>
  !!draft.value && (draft.value.completeness.missing.includes(field.name) || draft.value.completeness.proposed.includes(field.name));

const staleFields = computed(() => draft.value?.fields.filter((f) => f.stale) ?? []);
const proposedCount = computed(() => draft.value?.fields.filter((f) => f.current.status === "proposé" && f.current.value !== null).length ?? 0);

/** Change à chaque modification des valeurs : sert à rafraîchir l'aperçu. */
const previewSignature = computed(() => draft.value?.fields.map((f) => f.current.id).join("|") ?? "");

// --- Actions sur un champ ---

const validateField = (name: string) => run(() => api.validate(draftId, name));
const rejectField = (name: string, reason: string) => run(() => api.reject(draftId, name, reason));
const saveField = (name: string, value: FieldValue, reason: string) => run(() => api.setValue(draftId, name, value, reason));
const regenerateField = (name: string, instruction: string) =>
  run(() => api.regenerateField(draftId, name, instruction), "L'agent régénère ce champ…");
const validateAll = () => run(() => api.validateAll(draftId), "Valeurs proposées validées.");
const proposeValues = () => run(() => api.generateValues(draftId), "L'agent propose des valeurs…");

// --- Historique d'un champ ---

const historyField = ref<DraftField | null>(null);
const historyVersions = ref<FieldVersion[]>([]);
const historyLoading = ref(false);

async function openHistory(field: DraftField) {
  historyField.value = field;
  historyLoading.value = true;
  try {
    historyVersions.value = (await api.fetchFieldVersions(draftId, field.name)).reverse();
  } catch (e) {
    error.value = draftErrorMessage(e, "Impossible de charger l'historique.");
    historyField.value = null;
  } finally {
    historyLoading.value = false;
  }
}

async function restoreVersion(versionId: string) {
  const field = historyField.value;
  if (!field) return;
  historyField.value = null;
  await run(() => api.restoreFieldVersion(draftId, field.name, versionId), "Valeur restaurée (ajoutée comme nouvelle version).");
}

// --- Génération du document ---

const confirmIncomplete = ref<string[] | null>(null);

async function generateDocument(confirm = false) {
  busy.value = true;
  error.value = "";
  info.value = "";
  confirmIncomplete.value = null;
  try {
    generated.value = await api.generateDocument(draftId, confirm);
  } catch (e) {
    const incomplete = incompleteFieldsFrom(e);
    if (incomplete) confirmIncomplete.value = incomplete;
    else error.value = draftErrorMessage(e, "Impossible de générer le document.");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="review">
    <BackLink :to="`/dossiers/${dossierId}/documents`">
      Documents du dossier
    </BackLink>

    <p v-if="loading" class="fr-text--sm">Chargement…</p>
    <DsfrAlert v-else-if="!draft" type="error" :description="error || 'Brouillon introuvable.'" />

    <template v-else>
      <header class="review__header">
        <h1 class="fr-h3">{{ draft.templateName }}</h1>
        <DsfrBadge :label="`Modèle version ${draft.templateVersionNumber}`" small />
        <DsfrBadge :label="`Analyse : révision ${draft.revisionNumber}`" type="info" small />
        <DsfrBadge v-if="draft.status !== 'brouillon'" :label="draft.status" type="warning" small />
      </header>

      <DsfrAlert v-if="error" type="error" :description="error" small />
      <DsfrAlert v-if="info" type="success" :description="info" small />

      <!-- Le document qui vient d'être généré, avec ses téléchargements -->
      <DsfrAlert v-if="generated" type="success" small>
        <template #default>
          Document version {{ generated.versionNumber }} (modèle v{{ generated.templateVersionNumber }}, analyse révision {{ generated.revisionNumber }}) :
          <a :href="api.documentUrl(generated.id, 'odt')" class="fr-link">Télécharger l'ODT</a>
          <template v-if="generated.hasPdf"> · <a :href="api.documentUrl(generated.id, 'pdf')" class="fr-link">Télécharger le PDF</a></template>
          · <RouterLink :to="`/dossiers/${dossierId}/documents`" class="fr-link">Voir les documents du dossier</RouterLink>
        </template>
      </DsfrAlert>

      <!-- Version de l'analyse et valeurs sources modifiées depuis -->
      <DsfrAlert
        v-if="staleFields.length"
        type="warning"
        small
        :description="`Des éléments de l'analyse ont été modifiés depuis la révision ${draft.revisionNumber} dont ce brouillon est tiré : ${staleFields.map((f) => f.label).join(', ')}. Les valeurs ci-dessous restent celles de la révision.`"
      />

      <!-- Suivi de l'agent -->
      <DsfrAlert v-if="generating" type="info" small description="L'agent propose des valeurs… Les champs se mettent à jour dès qu'il a terminé." />
      <DsfrAlert v-else-if="draft.generationStatus === 'échec'" type="error" small :description="`La génération par l'agent a échoué : ${draft.generationError ?? 'erreur inconnue'}`" />
      <DsfrAlert
        v-else-if="draft.generationStatus === 'terminé'"
        type="info"
        small
        :description="
          `L'agent a proposé ${draft.generationProposalCount ?? 0} valeur(s)` +
          (draft.generationMissing?.length ? `, rien trouvé pour : ${draft.generationMissing.map(labelOf).join(', ')}` : '') +
          (draft.generationTruncated ? '. Le contexte était trop volumineux et a été tronqué : vérifiez les valeurs.' : '.')
        "
      />

      <!-- Complétude -->
      <DsfrAlert
        v-if="draft.completeness.complete"
        type="success"
        small
        description="Tous les champs obligatoires sont validés : le document peut être généré."
      />
      <DsfrAlert
        v-else
        type="warning"
        small
        :description="
          [
            draft.completeness.missing.length ? `À renseigner : ${draft.completeness.missing.map(labelOf).join(', ')}.` : '',
            draft.completeness.proposed.length ? `À valider : ${draft.completeness.proposed.map(labelOf).join(', ')}.` : '',
          ].join(' ')
        "
      />

      <div class="review__toolbar">
        <DsfrButton
          label="Proposer des valeurs (agent)"
          icon="ri-sparkling-2-fill"
          secondary
          :disabled="!editable || generating"
          @click="proposeValues"
        />
        <DsfrButton label="Valider les propositions" tertiary :disabled="!editable || proposedCount === 0" @click="validateAll" />
        <DsfrButton label="Générer le document" icon="ri-file-word-2-line" :disabled="!editable" @click="generateDocument(false)" />
      </div>


      <div class="review__body">
        <ul class="review__fields" aria-label="Champs du document">
          <DraftFieldCard
            v-for="field in draft.fields"
            :key="field.name"
            :field="field"
            :editable="editable"
            :generating="generating"
            :attention="needsAttention(field)"
            @validate="validateField(field.name)"
            @reject="rejectField(field.name, $event)"
            @save="(value, reason) => saveField(field.name, value, reason)"
            @regenerate="regenerateField(field.name, $event)"
            @history="openHistory(field)"
          />
        </ul>
        <aside class="review__preview">
          <PdfPreview :signature="previewSignature" :load="() => api.fetchPreview(draftId)" />
        </aside>
      </div>
    </template>

    <FieldHistoryModal
      :field="historyField"
      :versions="historyVersions"
      :loading="historyLoading"
      :can-restore="editable"
      @close="historyField = null"
      @restore="restoreVersion"
    />

    <DsfrModal
      :opened="confirmIncomplete !== null"
      title="Générer un document incomplet ?"
      icon="ri-alert-line"
      :actions="[
        { label: 'Annuler', secondary: true, onClick: () => (confirmIncomplete = null) },
        { label: 'Générer quand même', onClick: () => generateDocument(true) },
      ]"
      @close="confirmIncomplete = null"
    >
      <p>
        Ces champs obligatoires ne sont pas validés : <strong>{{ confirmIncomplete?.map(labelOf).join(', ') }}</strong>.
      </p>
      <p class="fr-text--sm">Ils seront écrits « [non renseigné] » dans le document, et cela sera consigné.</p>
    </DsfrModal>
  </div>
</template>

<style scoped>
.review {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.review__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.review__header h1 {
  margin: 0;
}

.review__toolbar {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.review__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1.5rem;
  align-items: start;
}

.review__fields {
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.review__preview {
  min-width: 0;
}

@media (min-width: 1200px) {
  .review__body {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .review__preview {
    position: sticky;
    top: 1rem;
    height: calc(100vh - 2rem);
  }
}
</style>
