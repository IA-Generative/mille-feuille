<script setup lang="ts">
import { computed, ref } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { FIELD_TYPE_LABELS, type CustomField, type CustomValue, type FieldType } from "@/types/tracking";
import { userMessage } from "@/utils/api";
import ErrorList from "@/components/ErrorList.vue";

// Définition des colonnes personnalisées (administrateurs). Versionnée avec historique et restauration, comme les
// autres champs d'une analyse (cf. VersionHistory). Le serveur valide la définition (noms uniques, au plus 20 champs,
// valeurs par défaut cohérentes) ; ses messages s'affichent sous la liste.
const props = defineProps<{ analyseId: string }>();
const emit = defineEmits<{ close: []; saved: [message: string] }>();

const { getById, updateCustomFields, restoreCustomFieldsVersion } = useAnalyses();
const analyse = computed(() => getById(props.analyseId));
const fields = computed(() => analyse.value?.customFields ?? []);
const fieldsVersions = computed(() => analyse.value?.customFieldsVersions ?? []);

const MAX_FIELDS = 20;

const draft = ref<CustomField[]>(JSON.parse(JSON.stringify(fields.value)));
const openId = ref<string | null>(null);
const purge = ref(false);
const removed = ref<CustomField[]>([]);
const choicesText = ref<Record<string, string>>(Object.fromEntries(draft.value.map((f) => [f.id, f.choices.join("\n")])));
/** Identifiants provisoires des champs créés ici : le serveur leur donne leur identifiant définitif à l'enregistrement. */
const newIds = ref<Set<string>>(new Set());
const saving = ref(false);
const saveError = ref("");

const typeOptions = Object.entries(FIELD_TYPE_LABELS) as [FieldType, string][];

function addField() {
  if (draft.value.length >= MAX_FIELDS) return;
  const id = `new-${Date.now()}`;
  newIds.value.add(id);
  draft.value.push({ id, name: "", definition: "", type: "text", required: false, defaultValue: null, choices: [], currency: "EUR" });
  choicesText.value[id] = "";
  openId.value = id;
}

function removeField(f: CustomField) {
  draft.value = draft.value.filter((x) => x.id !== f.id);
  if (fields.value.some((x) => x.id === f.id)) removed.value.push(f);
}

function undoRemove(f: CustomField) {
  removed.value = removed.value.filter((x) => x.id !== f.id);
  draft.value.push(f);
}

function setChoices(f: CustomField, text: string) {
  choicesText.value[f.id] = text;
  f.choices = text.split("\n").map((c) => c.trim()).filter(Boolean);
  if (f.defaultValue !== null && !f.choices.includes(String(f.defaultValue))) f.defaultValue = null;
}

function setType(f: CustomField, type: FieldType) {
  f.type = type;
  f.defaultValue = type === "boolean" ? false : null;
}

function setDefault(f: CustomField, raw: string) {
  f.defaultValue = raw === "" ? null : f.type === "number" || f.type === "amount" ? Number(raw) : raw;
}

/** Les champs dont le type change perdent leurs valeurs : on prévient avant d'enregistrer. */
const retyped = computed(() =>
  draft.value.filter((f) => !newIds.value.has(f.id) && fields.value.find((x) => x.id === f.id)?.type !== f.type),
);

const errors = computed(() => {
  const list: string[] = [];
  const names = new Set<string>();
  for (const f of draft.value) {
    const name = f.name.trim();
    if (!name) list.push("Chaque champ doit avoir un nom.");
    else if (names.has(name.toLowerCase())) list.push(`Le nom « ${name} » est utilisé deux fois.`);
    names.add(name.toLowerCase());
    if (f.type === "choice" && f.choices.length === 0) list.push(`« ${name || "Champ"} » : ajoutez au moins un choix.`);
  }
  return [...new Set(list)];
});

const dirty = computed(() => JSON.stringify(draft.value) !== JSON.stringify(fields.value) || (removed.value.length > 0 && purge.value));

async function save() {
  if (errors.value.length || saving.value) return;
  saving.value = true;
  saveError.value = "";
  try {
    await updateCustomFields(
      props.analyseId,
      draft.value.map((f) => ({ ...f, name: f.name.trim() })),
      purge.value,
      newIds.value,
    );
    emit("saved", "Colonnes personnalisées enregistrées. L'ancienne version est dans l'historique.");
    emit("close");
  } catch (e) {
    saveError.value = userMessage(e, "L'enregistrement a échoué.");
  } finally {
    saving.value = false;
  }
}

async function restore(versionId: string) {
  saveError.value = "";
  try {
    await restoreCustomFieldsVersion(props.analyseId, versionId);
    emit("saved", "Version restaurée.");
    emit("close");
  } catch (e) {
    saveError.value = userMessage(e, "La restauration a échoué.");
  }
}

const summarize = (content: CustomField[]) =>
  content.length === 0 ? "Aucun champ" : content.map((f) => `${f.name} (${FIELD_TYPE_LABELS[f.type].toLowerCase()})`).join(", ");

const actions = computed(() => [
  { label: saving.value ? "Enregistrement…" : "Enregistrer", disabled: !dirty.value || errors.value.length > 0 || saving.value, onClick: save },
  { label: "Annuler", secondary: true, onClick: () => emit("close") },
]);

const defaultInputType = (f: CustomField) => (f.type === "date" ? "date" : f.type === "text" ? "text" : "number");
const defaultAsString = (v: CustomValue) => (v === null ? "" : String(v));
</script>

<template>
  <DsfrModal :opened="true" title="Colonnes personnalisées" icon="ri-table-line" size="lg" :actions="actions" @close="emit('close')">
    <p class="cf__hint">
      Définissez les informations propres à votre métier à suivre pour chaque dossier. Chaque modification crée une version restaurable.
    </p>

    <ul class="cf__list">
      <li v-for="f in draft" :key="f.id" class="cf__item">
        <button type="button" class="cf__head" :aria-expanded="openId === f.id" @click="openId = openId === f.id ? null : f.id">
          <VIcon :name="openId === f.id ? 'ri-arrow-down-s-line' : 'ri-arrow-right-s-line'" />
          <strong>{{ f.name || "Nouveau champ" }}</strong>
          <span class="cf__meta">{{ FIELD_TYPE_LABELS[f.type] }}{{ f.required ? " · obligatoire" : "" }}</span>
        </button>

        <div v-if="openId === f.id" class="cf__body">
          <div class="cf__grid">
            <div>
              <label :for="`cf-name-${f.id}`">Nom</label>
              <input :id="`cf-name-${f.id}`" v-model="f.name" class="fr-input" type="text" />
            </div>
            <div class="cf__wide">
              <label :for="`cf-def-text-${f.id}`">Définition (affichée en aide dans l'en-tête de la colonne)</label>
              <textarea :id="`cf-def-text-${f.id}`" v-model="f.definition" class="fr-input" rows="2" placeholder="Que représente ce champ, comment le remplir ? Une définition précise servira aussi à pré-remplir les valeurs par l'IA (suite possible)." />
            </div>
            <div>
              <label :for="`cf-type-${f.id}`">Type</label>
              <select :id="`cf-type-${f.id}`" class="fr-select" :value="f.type" @change="setType(f, ($event.target as HTMLSelectElement).value as FieldType)">
                <option v-for="[value, label] in typeOptions" :key="value" :value="value">{{ label }}</option>
              </select>
            </div>
            <div v-if="f.type === 'amount'">
              <label :for="`cf-cur-${f.id}`">Devise</label>
              <select :id="`cf-cur-${f.id}`" v-model="f.currency" class="fr-select">
                <option value="EUR">Euro (EUR)</option>
                <option value="USD">Dollar (USD)</option>
                <option value="GBP">Livre (GBP)</option>
              </select>
            </div>
            <div v-if="f.type === 'choice'" class="cf__wide">
              <label :for="`cf-choices-${f.id}`">Choix possibles (un par ligne)</label>
              <textarea :id="`cf-choices-${f.id}`" class="fr-input" rows="4" :value="choicesText[f.id]" @input="setChoices(f, ($event.target as HTMLTextAreaElement).value)" />
            </div>
            <div v-if="f.type !== 'boolean'">
              <label :for="`cf-def-${f.id}`">Valeur par défaut</label>
              <select v-if="f.type === 'choice'" :id="`cf-def-${f.id}`" class="fr-select" :value="defaultAsString(f.defaultValue)" @change="setDefault(f, ($event.target as HTMLSelectElement).value)">
                <option value="">Aucune</option>
                <option v-for="c in f.choices" :key="c" :value="c">{{ c }}</option>
              </select>
              <input v-else :id="`cf-def-${f.id}`" class="fr-input" :type="defaultInputType(f)" :value="defaultAsString(f.defaultValue)" @input="setDefault(f, ($event.target as HTMLInputElement).value)" />
            </div>
            <label class="cf__check">
              <input v-model="f.required" type="checkbox" /> Obligatoire
            </label>
          </div>
          <button type="button" class="cf__remove" @click="removeField(f)"><VIcon name="ri-delete-bin-line" /> Supprimer ce champ</button>
        </div>
      </li>
    </ul>

    <button
      type="button"
      class="fr-btn fr-btn--sm fr-btn--secondary"
      style="gap: 0.375rem"
      :disabled="draft.length >= MAX_FIELDS"
      @click="addField"
    >
      <VIcon name="ri-add-line" /> Ajouter un champ
    </button>
    <span v-if="draft.length >= MAX_FIELDS" class="cf__hint">Vingt champs au plus par analyse.</span>

    <div v-if="removed.length" class="cf__removed" role="status">
      <p>
        {{ removed.length }} champ{{ removed.length > 1 ? "s" : "" }} supprimé{{ removed.length > 1 ? "s" : "" }} :
        <span v-for="f in removed" :key="f.id" class="cf__undo">{{ f.name }} <button type="button" @click="undoRemove(f)">Annuler</button></span>
      </p>
      <fieldset class="cf__purge">
        <legend>Que faire des valeurs déjà saisies ?</legend>
        <label><input v-model="purge" type="radio" :value="false" /> Les conserver (récupérables si le champ revient)</label>
        <label><input v-model="purge" type="radio" :value="true" /> Les supprimer définitivement</label>
      </fieldset>
    </div>

    <p v-if="retyped.length" class="cf__warn" role="status">
      <VIcon name="ri-alert-line" /> Changer le type de {{ retyped.map((f) => `« ${f.name || "Champ"} »`).join(", ") }} supprime
      les valeurs déjà saisies dans ce champ.
    </p>

    <ErrorList :errors="errors" class="fr-mt-2w" />

    <DsfrAlert v-if="saveError" alert type="error" small :description="saveError" class="fr-mt-2w" />

    <div class="cf__history">
      <VersionHistory :versions="fieldsVersions" :format-content="summarize" @restore="restore" />
    </div>
  </DsfrModal>
</template>

<style scoped>
.cf__warn {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin: 0.75rem 0 0;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  background: var(--background-contrast-warning);
  font-size: 0.875rem;
}

.cf__hint {
  margin: 0 0 0.75rem;
  color: var(--text-mention-grey);
  font-size: 0.875rem;
}

.cf__list {
  margin: 0 0 0.75rem;
  padding: 0;
  list-style: none;
}

.cf__item {
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  margin-bottom: 0.5rem;
}

.cf__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.625rem 0.75rem;
  border: none;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.cf__meta {
  margin-left: auto;
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.cf__body {
  padding: 0.25rem 0.75rem 0.75rem;
}

.cf__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: 0.75rem;
  align-items: end;
}

.cf__grid label:not(.cf__check) {
  display: block;
  margin-bottom: 0.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
}

.cf__wide {
  grid-column: 1 / -1;
}

.cf__check {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.cf__remove {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  margin-top: 0.75rem;
  padding: 0;
  border: none;
  background: none;
  color: var(--text-default-error);
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}

.cf__removed {
  margin-top: 1rem;
  padding: 0.75rem;
  border-radius: 0.5rem;
  background: var(--background-alt-grey);
  font-size: 0.875rem;
}

.cf__removed p {
  margin: 0 0 0.5rem;
}

.cf__undo {
  margin-left: 0.5rem;
}

.cf__undo button {
  padding: 0;
  border: none;
  background: none;
  color: var(--text-action-high-blue-france);
  font: inherit;
  text-decoration: underline;
  cursor: pointer;
}

.cf__purge {
  margin: 0;
  padding: 0;
  border: none;
}

.cf__purge legend {
  margin-bottom: 0.25rem;
  font-weight: 600;
}

.cf__purge label {
  display: block;
}

.cf__history {
  margin-top: 1rem;
}
</style>
