<script setup lang="ts">
import { computed, ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import {
  errorMessage,
  placeholderReportFrom,
  sourcesReportFrom,
  useDocumentTemplates,
} from "@/composables/useDocumentTemplates";
import { suggestTemplateDescription, suggestTemplateInstructions } from "@/composables/useLlmAssist";
import type { Version } from "@/types/analyse";
import type {
  AnalyseDefinitions,
  DocumentTemplate,
  DocumentTemplateVersion,
  FieldDefinition,
  ImportWarning,
  PlaceholderReport,
  SourcesReport,
} from "@/types/documentTemplate";
import { defaultField, isValidFieldName, validateTemplate } from "@/utils/documentTemplateValidation";

import AssistedTextarea from "./AssistedTextarea.vue";
import TemplateFieldRow from "./TemplateFieldRow.vue";

/** Écrit un placeholder comme dans le fichier : {{ nom }} (hors gabarit, où « }} » fermerait l'interpolation). */
const braces = (name: string) => `{{ ${name} }}`;

// Création et modification d'un modèle de document : import du fichier ODT, définition des champs, rapport de
// validation (bloquant) et historique des versions. Enregistrer ajoute une version, rien n'est écrasé.
const props = defineProps<{ template: DocumentTemplate | null; analyseId: string; analyseName: string }>();
const emit = defineEmits<{ saved: [DocumentTemplate]; cancel: []; changed: [] }>();

const api = useDocumentTemplates();

/** Copie profonde d'un objet éventuellement réactif (structuredClone refuse les proxys Vue). */
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value));

const current = ref<DocumentTemplate | null>(props.template);
const isNew = computed(() => current.value === null);

const name = ref(props.template?.name ?? "");
const description = ref(props.template?.description ?? "");
const generationInstructions = ref(props.template?.generationInstructions ?? "");
// Contrôle à l'import : ce qui risque de surprendre (police absente de l'image, champ natif LibreOffice, image).
// À lire, jamais bloquant.
const importWarnings = ref<ImportWarning[]>([...(props.template?.warnings ?? [])]);
const fields = ref<FieldDefinition[]>(clone(props.template?.fields ?? []));
const placeholders = ref<string[]>([...(props.template?.placeholders ?? [])]);
const file = ref<File | null>(null);
const fileLabel = ref(props.template ? `${props.template.fileName} (version ${props.template.versionNumber})` : "");

const inspecting = ref(false);
const saving = ref(false);
const error = ref("");
const info = ref("");
const serverReport = ref<PlaceholderReport | null>(null);
const sourcesReport = ref<SourcesReport | null>(null);
// Ce que l'analyse du modèle définit : les choix de la source d'un champ, et de quoi vérifier ceux déjà posés.
const definitions = ref<AnalyseDefinitions | null>(null);
api
  .fetchDefinitions(props.analyseId)
  .then((d) => (definitions.value = d))
  .catch(() => (definitions.value = null));
const newFieldName = ref("");
const versions = ref<DocumentTemplateVersion[]>([]);

// Carrousel : un seul champ est édité à la fois, les pastilles donnent l'état de chacun.
const activeIndex = ref(0);
const activeField = computed(() => fields.value[activeIndex.value] ?? null);
watch(
  () => fields.value.length,
  (count) => {
    if (activeIndex.value >= count) activeIndex.value = Math.max(0, count - 1);
  },
);

const issues = computed(() => validateTemplate(placeholders.value, fields.value, definitions.value));
const issuesByField = (fieldName: string) => issues.value.filter((i) => i.name === fieldName && i.kind !== "unknown_placeholder");
const unknownPlaceholders = computed(() => issues.value.filter((i) => i.kind === "unknown_placeholder"));
const fieldHasIssue = (fieldName: string) => issuesByField(fieldName).length > 0;

function previous() {
  activeIndex.value = Math.max(0, activeIndex.value - 1);
}

function next() {
  activeIndex.value = Math.min(fields.value.length - 1, activeIndex.value + 1);
}

/** Va au premier champ qui a un point à corriger. */
function goToFirstIssue() {
  const index = fields.value.findIndex((f) => fieldHasIssue(f.name) || !f.name);
  if (index !== -1) activeIndex.value = index;
}

const canSave = computed(
  () => name.value.trim().length > 0 && issues.value.length === 0 && (!isNew.value || file.value !== null) && !saving.value,
);

async function loadVersions() {
  if (!current.value) return;
  try {
    // De la plus récente à la plus ancienne.
    versions.value = (await api.fetchVersions(current.value.id)).reverse();
  } catch {
    versions.value = [];
  }
}
void loadVersions();

async function onFileChange(event: Event) {
  const chosen = (event.target as HTMLInputElement).files?.[0] ?? null;
  error.value = "";
  info.value = "";
  serverReport.value = null;
  sourcesReport.value = null;
  if (!chosen) return;
  inspecting.value = true;
  try {
    const result = await api.inspectFile(chosen);
    file.value = chosen;
    fileLabel.value = `${chosen.name} (nouveau fichier)`;
    placeholders.value = result.placeholders;
    importWarnings.value = result.warnings;
    // Un champ par placeholder détecté ; ceux déjà définis sont conservés tels quels.
    const known = new Set(fields.value.map((f) => f.name));
    const added = result.placeholders.filter((p) => !known.has(p));
    const firstAdded = fields.value.length;
    fields.value = [...fields.value, ...added.map(defaultField)];
    if (added.length) activeIndex.value = firstAdded;
    info.value = `${result.placeholders.length} placeholder(s) détecté(s) dans le fichier` + (added.length ? `, ${added.length} champ(s) à définir.` : ".");
  } catch (e) {
    file.value = null;
    error.value = errorMessage(e, "Impossible de lire ce fichier.");
  } finally {
    inspecting.value = false;
  }
}

function addField() {
  const fieldName = newFieldName.value.trim();
  if (!fieldName) return;
  fields.value = [...fields.value, defaultField(fieldName)];
  activeIndex.value = fields.value.length - 1;
  newFieldName.value = "";
}

const newFieldNameInvalid = computed(() => newFieldName.value.trim() !== "" && !isValidFieldName(newFieldName.value.trim()));

function updateField(index: number, value: FieldDefinition) {
  fields.value = fields.value.map((f, i) => (i === index ? value : f));
}

function removeField(index: number) {
  fields.value = fields.value.filter((_, i) => i !== index);
}

function defineUnknown(fieldName: string) {
  fields.value = [...fields.value, defaultField(fieldName)];
  activeIndex.value = fields.value.length - 1;
}

/** Recharge l'éditeur depuis le modèle renvoyé par le serveur (après enregistrement ou restauration). */
function load(template: DocumentTemplate) {
  current.value = template;
  name.value = template.name;
  description.value = template.description;
  generationInstructions.value = template.generationInstructions;
  fields.value = clone(template.fields);
  placeholders.value = [...template.placeholders];
  importWarnings.value = [...template.warnings];
  activeIndex.value = Math.min(activeIndex.value, Math.max(0, template.fields.length - 1));
  file.value = null;
  fileLabel.value = `${template.fileName} (version ${template.versionNumber})`;
  void loadVersions();
}

async function save() {
  saving.value = true;
  error.value = "";
  info.value = "";
  serverReport.value = null;
  sourcesReport.value = null;
  const draft = {
    analyseId: props.analyseId,
    name: name.value,
    description: description.value,
    generationInstructions: generationInstructions.value,
    fields: fields.value,
    file: file.value,
  };
  try {
    const saved = current.value ? await api.addVersion(current.value.id, draft) : await api.createTemplate(draft);
    load(saved);
    info.value = `Version ${saved.versionNumber} enregistrée.`;
    emit("saved", saved);
  } catch (e) {
    serverReport.value = placeholderReportFrom(e);
    sourcesReport.value = sourcesReportFrom(e);
    error.value = serverReport.value || sourcesReport.value ? "" : errorMessage(e, "Erreur lors de l'enregistrement.");
  } finally {
    saving.value = false;
  }
}

const versionItems = computed<Version<DocumentTemplateVersion>[]>(() =>
  versions.value.map((v) => ({ id: v.id, content: v, createdAt: v.createdAt })),
);

function formatVersion(v: DocumentTemplateVersion) {
  const restored = v.restoredFromVersionId ? " · restaurée" : "";
  return `Version ${v.versionNumber} — ${v.name} · ${v.fields.length} champ(s) · ${v.fileName}${restored}`;
}

async function restore(versionId: string) {
  if (!current.value) return;
  if (!confirm("Restaurer cette version ? Une nouvelle version, identique à elle, sera ajoutée.")) return;
  error.value = "";
  info.value = "";
  try {
    const restored = await api.restoreVersion(current.value.id, versionId);
    load(restored);
    info.value = `Version ${restored.versionNumber} ajoutée (restauration).`;
    emit("saved", restored);
  } catch (e) {
    error.value = errorMessage(e, "Impossible de restaurer cette version.");
  }
}

async function toggleArchive() {
  if (!current.value) return;
  error.value = "";
  try {
    const updated = await api.setArchived(current.value.id, !current.value.archived);
    current.value = updated;
    info.value = updated.archived ? "Modèle archivé : il n'est plus proposé pour de nouveaux documents." : "Modèle désarchivé.";
    emit("changed");
  } catch (e) {
    error.value = errorMessage(e, "Impossible de modifier l'archivage.");
  }
}

const downloadUrl = computed(() => (current.value ? api.fileUrl(current.value.id, current.value.versionNumber) : ""));
</script>

<template>
  <section class="template-editor" aria-label="Édition d'un modèle de document">
    <div class="template-editor__top">
      <DsfrButton label="Retour à la liste" icon="ri-arrow-left-line" tertiary size="sm" @click="emit('cancel')" />
      <h3 class="fr-h5 template-editor__title">
        {{ isNew ? "Nouveau modèle de document" : name || "Modèle" }}
        <DsfrBadge v-if="current" :label="`Version ${current.versionNumber}`" small />
        <DsfrBadge :label="analyseName" type="info" small />
        <DsfrBadge v-if="current?.archived" label="Archivé" type="warning" small />
      </h3>
    </div>

    <DsfrAlert v-if="error" type="error" :description="error" small />
    <DsfrAlert v-if="info" type="success" :description="info" small />

    <div v-if="serverReport" class="template-editor__report" role="alert">
      <p class="fr-text--bold">{{ serverReport.message }}</p>
      <ul>
        <li v-for="p in serverReport.unknownPlaceholders" :key="'u' + p">
          Le placeholder <code>{{ braces(p) }}</code> n'a pas de champ défini.
        </li>
        <li v-for="f in serverReport.unusedFields" :key="'f' + f">
          Le champ <code>{{ f }}</code> n'a pas de placeholder dans le fichier.
        </li>
      </ul>
    </div>

    <div v-if="sourcesReport" class="template-editor__report" role="alert">
      <p class="fr-text--bold">{{ sourcesReport.message }}</p>
      <ul>
        <li v-for="u in sourcesReport.unknownSources" :key="u.field">
          Le champ <code>{{ u.field }}</code> désigne « {{ u.definitionName }} », que l'analyse ne définit pas.
        </li>
      </ul>
    </div>

    <fieldset class="template-editor__block">
      <legend class="fr-h6">Le modèle</legend>
      <p class="fr-text--sm template-editor__analyse">
        Analyse : <strong>{{ analyseName }}</strong> — ce modèle ne sert qu'aux dossiers de cette analyse.
      </p>
      <DsfrInput v-model="name" label="Nom" label-visible hint="Unique, majuscules et accents ignorés" />
      <AssistedTextarea
        v-model="description"
        label="Description"
        :rows="2"
        assist-label="Suggérer une description"
        :suggest="(draft, model) => suggestTemplateDescription(draft, { name }, model)"
      />
      <AssistedTextarea
        v-model="generationInstructions"
        label="Consignes générales de génération"
        hint="Ton, registre, langue : communes à tous les champs (facultatif)"
        :rows="3"
        assist-label="Suggérer des consignes"
        :suggest="(draft, model) => suggestTemplateInstructions(draft, { name, description }, model)"
      />
    </fieldset>

    <fieldset class="template-editor__block">
      <legend class="fr-h6">Le fichier</legend>
      <p v-if="fileLabel" class="fr-text--sm template-editor__file">
        {{ fileLabel }}
        <a v-if="current && !file" :href="downloadUrl" class="fr-link fr-link--sm" download>Télécharger</a>
      </p>
      <div v-if="importWarnings.length" class="template-editor__warnings" role="status">
        <p class="fr-text--sm fr-text--bold">À vérifier dans ce fichier (n'empêche pas l'enregistrement) :</p>
        <ul>
          <li v-for="w in importWarnings" :key="w.code + w.message" :class="`template-editor__warning--${w.level}`">
            <span aria-hidden="true">{{ w.level === "warning" ? "⚠" : "ℹ" }}</span> {{ w.message }}
          </li>
        </ul>
      </div>
      <div class="fr-upload-group">
        <label class="fr-label" for="template-file">
          {{ isNew ? "Fichier du modèle (ODT)" : "Remplacer le fichier (ODT)" }}
          <span class="fr-hint-text">
            Document LibreOffice Writer avec des champs {{ braces("nom") }}. Le fichier est lu pour détecter ses champs.
          </span>
        </label>
        <input
          id="template-file"
          class="fr-upload"
          type="file"
          accept=".odt,application/vnd.oasis.opendocument.text"
          :disabled="inspecting"
          @change="onFileChange"
        />
      </div>
    </fieldset>

    <fieldset class="template-editor__block">
      <legend class="fr-h6">Les champs ({{ fields.length }})</legend>

      <div
        class="template-editor__validation"
        :class="issues.length ? 'template-editor__validation--ko' : 'template-editor__validation--ok'"
        role="status"
      >
        <template v-if="issues.length === 0">
          <span aria-hidden="true">✔</span>
          Les champs correspondent aux placeholders du fichier.
        </template>
        <template v-else>
          <span aria-hidden="true">⚠</span>
          {{ issues.length }} point(s) à corriger avant d'enregistrer.
        </template>
      </div>

      <ul v-if="unknownPlaceholders.length" class="template-editor__unknown">
        <li v-for="issue in unknownPlaceholders" :key="issue.name">
          {{ issue.message }}
          <DsfrButton label="Définir ce champ" size="sm" tertiary @click="defineUnknown(issue.name)" />
        </li>
      </ul>

      <p v-if="fields.length === 0" class="fr-text--sm">
        Aucun champ. Choisissez un fichier : un champ est créé pour chaque placeholder détecté.
      </p>
      <div v-if="fields.length" class="template-editor__carousel">
        <div class="template-editor__carousel-nav">
          <DsfrButton label="Précédent" icon="ri-arrow-left-s-line" tertiary size="sm" :disabled="activeIndex === 0" @click="previous" />
          <div class="template-editor__chips" role="tablist" aria-label="Champs du modèle">
            <button
              v-for="(f, index) in fields"
              :id="`field-chip-${index}`"
              :key="f.name + index"
              type="button"
              role="tab"
              class="template-editor__chip"
              :class="{
                'template-editor__chip--active': index === activeIndex,
                'template-editor__chip--ko': fieldHasIssue(f.name),
              }"
              :aria-selected="index === activeIndex"
              @click="activeIndex = index"
            >
              <span aria-hidden="true">{{ fieldHasIssue(f.name) ? "⚠" : "✔" }}</span>
              {{ braces(f.name) }}
            </button>
          </div>
          <DsfrButton
            label="Suivant"
            icon="ri-arrow-right-s-line"
            icon-right
            tertiary
            size="sm"
            :disabled="activeIndex >= fields.length - 1"
            @click="next"
          />
        </div>
        <p class="fr-text--sm template-editor__carousel-caption">
          Champ {{ activeIndex + 1 }} sur {{ fields.length }}
          <DsfrButton
            v-if="issues.length"
            label="Aller au premier point à corriger"
            tertiary
            no-outline
            size="sm"
            @click="goToFirstIssue"
          />
        </p>
        <ul v-if="activeField" class="template-editor__fields" role="tabpanel" :aria-labelledby="`field-chip-${activeIndex}`">
          <TemplateFieldRow
            :model-value="activeField"
            :template-name="name"
            :definitions="definitions"
            :in-file="placeholders.includes(activeField.name)"
            :issues="issuesByField(activeField.name)"
            @update:model-value="updateField(activeIndex, $event)"
            @remove="removeField(activeIndex)"
          />
        </ul>
      </div>

      <div class="template-editor__add">
        <DsfrInput
          v-model="newFieldName"
          label="Ajouter un champ"
          label-visible
          hint="Nom du placeholder, sans les accolades"
          :is-invalid="newFieldNameInvalid"
          @keydown.enter.prevent="addField"
        />
        <DsfrButton label="Ajouter" secondary size="sm" :disabled="!newFieldName.trim() || newFieldNameInvalid" @click="addField" />
      </div>
    </fieldset>

    <div class="template-editor__actions">
      <DsfrButton :label="isNew ? 'Créer le modèle' : 'Enregistrer une nouvelle version'" :disabled="!canSave" @click="save" />
      <DsfrButton v-if="current" :label="current.archived ? 'Désarchiver' : 'Archiver'" secondary @click="toggleArchive" />
      <DsfrButton label="Annuler" tertiary @click="emit('cancel')" />
    </div>

    <VersionHistory v-if="current" :versions="versionItems" :format-content="formatVersion" @restore="restore" />
  </section>
</template>

<style scoped>
.template-editor {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.template-editor__top {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: flex-start;
}

.template-editor__title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin: 0;
}

.template-editor__block {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.375rem;
  padding: 1rem;
  margin: 0;
}

.template-editor__warnings {
  border-left: 4px solid var(--border-plain-warning, #b34000);
  background: var(--background-alt-grey);
  padding: 0.5rem 1rem;
}

.template-editor__warnings p {
  margin: 0 0 0.25rem;
}

.template-editor__warnings ul {
  margin: 0;
  padding-left: 1.25rem;
  list-style: none;
}

.template-editor__warnings li {
  margin: 0.25rem 0;
}

.template-editor__warning--warning {
  color: var(--text-default-warning, #b34000);
}

.template-editor__warning--info {
  color: var(--text-mention-grey);
}

.template-editor__analyse {
  margin: 0;
}

.template-editor__file {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
}

.template-editor__report {
  border-left: 4px solid var(--border-plain-error);
  background: var(--background-alt-red-marianne, var(--background-alt-grey));
  padding: 0.75rem 1rem;
}

.template-editor__report p {
  margin: 0 0 0.5rem;
}

.template-editor__validation {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  font-weight: 700;
}

.template-editor__validation--ok {
  color: var(--text-default-success);
  background: var(--background-contrast-success);
}

.template-editor__validation--ko {
  color: var(--text-default-error);
  background: var(--background-contrast-error);
}

.template-editor__unknown {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.template-editor__unknown li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  color: var(--text-default-error);
}

.template-editor__carousel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.template-editor__carousel-nav {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.template-editor__chips {
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  padding: 0.25rem;
  flex: 1;
  scroll-snap-type: x proximity;
}

.template-editor__chip {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 1rem;
  background: var(--background-default-grey);
  color: var(--text-default-grey);
  font-family: monospace;
  font-size: 0.875rem;
  cursor: pointer;
  scroll-snap-align: center;
}

.template-editor__chip--ko {
  border-color: var(--border-plain-error);
  color: var(--text-default-error);
}

.template-editor__chip--active {
  background: var(--background-action-high-blue-france);
  border-color: var(--background-action-high-blue-france);
  color: #fff;
  font-weight: 700;
}

/* Pastille active **et** en erreur : fond d'erreur plein, pour rester lisible. */
.template-editor__chip--active.template-editor__chip--ko {
  background: var(--background-flat-error, #ce0500);
  border-color: var(--background-flat-error, #ce0500);
  color: #fff;
}

.template-editor__carousel-caption {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  color: var(--text-mention-grey);
}

.template-editor__fields {
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.template-editor__add {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.template-editor__actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}
</style>
