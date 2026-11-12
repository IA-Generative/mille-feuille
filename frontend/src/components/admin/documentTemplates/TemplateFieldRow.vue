<script setup lang="ts">
import { computed } from "vue";

import ErrorList from "@/components/ErrorList.vue";
import {
  ELEMENT_KIND_LABELS,
  FIELD_TYPE_LABELS,
  METADATA_KEY_LABELS,
  SOURCE_KIND_LABELS,
  type AnalyseDefinitions,
  type ElementKind,
  type FieldDefinition,
  type FieldType,
  type MetadataKey,
  type SourceKind,
} from "@/types/documentTemplate";
import { suggestFieldInstruction } from "@/composables/useLlmAssist";
import type { ValidationIssue } from "@/utils/documentTemplateValidation";

import AssistedTextarea from "./AssistedTextarea.vue";

/** Écrit un placeholder comme dans le fichier : {{ nom }} (hors gabarit, où « }} » fermerait l'interpolation). */
const braces = (name: string) => `{{ ${name} }}`;

// Un champ d'un modèle de document : son libellé, son type, sa source et sa consigne de génération.
const props = defineProps<{
  modelValue: FieldDefinition;
  /** Ce que l'analyse du modèle définit : les choix possibles pour l'élément source (entités, labels, agents). */
  definitions?: AnalyseDefinitions | null;
  /** Nom du modèle, pour contextualiser l'aide à la rédaction de la consigne. */
  templateName?: string;
  /** Le fichier contient le placeholder {{ nom }}. */
  inFile: boolean;
  issues: ValidationIssue[];
}>();
const emit = defineEmits<{ "update:modelValue": [FieldDefinition]; remove: [] }>();

const issueMessages = computed(() => [...new Set(props.issues.map((issue) => issue.message))]);

function update(patch: Partial<FieldDefinition>) {
  emit("update:modelValue", { ...props.modelValue, ...patch });
}

const typeOptions = Object.entries(FIELD_TYPE_LABELS).map(([value, text]) => ({ value, text }));
const sourceOptions = Object.entries(SOURCE_KIND_LABELS).map(([value, text]) => ({ value, text }));
const elementKindOptions = Object.entries(ELEMENT_KIND_LABELS).map(([value, text]) => ({ value, text }));
const metadataOptions = Object.entries(METADATA_KEY_LABELS).map(([value, text]) => ({ value, text }));

const sourceKind = computed(() => props.modelValue.source.kind);

function changeSourceKind(kind: SourceKind) {
  if (kind === "analysis") update({ source: { kind, elementKind: "entity", definitionName: "" } });
  else if (kind === "dossier_metadata") update({ source: { kind, key: "dossier_name" } });
  else update({ source: { kind: "instruction" } });
}

const analysisSource = computed(() => (props.modelValue.source.kind === "analysis" ? props.modelValue.source : null));
/** Phrase décrivant d'où vient la valeur, pour l'aide à la rédaction. */
const sourceSentence = computed(() => {
  const source = props.modelValue.source;
  if (source.kind === "analysis") return `est tirée de l'élément « ${source.definitionName || "?"} » de l'analyse du dossier`;
  if (source.kind === "dossier_metadata") return `est la métadonnée « ${METADATA_KEY_LABELS[source.key]} »`;
  return "est renseignée par l'instructeur au fil de l'instruction du dossier";
});

function suggestInstruction(draft: string, model: string | null) {
  const f = props.modelValue;
  return suggestFieldInstruction(
    draft,
    { templateName: props.templateName ?? "", label: f.label, name: f.name, type: FIELD_TYPE_LABELS[f.type], source: sourceSentence.value },
    model,
  );
}

/** Noms proposés pour l'élément source, selon son type ; vide pour une relation ou un champ renseigné (texte libre). */
const elementChoices = computed<string[] | null>(() => {
  const source = analysisSource.value;
  if (!source || !props.definitions) return null;
  if (source.elementKind === "entity" || source.elementKind === "classification" || source.elementKind === "synthesis") {
    return props.definitions[source.elementKind];
  }
  return null;
});

/** Options du choix de l'élément : celles de l'analyse, plus la valeur actuelle si l'analyse ne la définit plus. */
const elementOptions = computed(() => {
  const current = analysisSource.value?.definitionName ?? "";
  const names = elementChoices.value ?? [];
  const options = [{ value: "", text: names.length ? "Choisir un élément…" : "L'analyse n'en définit aucun" }];
  if (current && !names.some((n) => n.toLowerCase() === current.trim().toLowerCase())) {
    options.push({ value: current, text: `${current} (inconnu dans l'analyse)` });
  }
  return [...options, ...names.map((n) => ({ value: n, text: n }))];
});

const metadataSource = computed(() => (props.modelValue.source.kind === "dossier_metadata" ? props.modelValue.source : null));
</script>

<template>
  <li class="field-row" :class="{ 'field-row--invalid': issues.length > 0 }">
    <div class="field-row__header">
      <code class="field-row__name">{{ braces(modelValue.name) }}</code>
      <DsfrBadge v-if="!inFile" label="Absent du fichier" type="warning" small />
      <DsfrBadge :label="modelValue.required ? 'Obligatoire' : 'Facultatif'" :type="modelValue.required ? 'info' : 'new'" small />
      <DsfrButton
        v-if="!inFile"
        label="Supprimer"
        icon="ri-delete-bin-line"
        tertiary
        no-outline
        size="sm"
        class="field-row__remove"
        @click="emit('remove')"
      />
    </div>

    <!-- Chaque composant DSFR a plusieurs nœuds racine : sans <div>, ils deviendraient des cellules distinctes. -->
    <div class="field-row__grid">
      <div>
        <DsfrInput
          :model-value="modelValue.label"
          label="Libellé"
          label-visible
          hint="Affiché à l'instructeur"
          @update:model-value="update({ label: String($event) })"
        />
      </div>
      <div>
        <DsfrSelect
          :model-value="modelValue.type"
          label="Type"
          label-visible
          :options="typeOptions"
          @update:model-value="update({ type: $event as FieldType })"
        />
      </div>
      <div class="field-row__required">
        <DsfrCheckbox
          :model-value="modelValue.required"
          :name="`required-${modelValue.name}`"
          label="Champ obligatoire"
          @update:model-value="update({ required: Boolean($event) })"
        />
      </div>
    </div>

    <div class="field-row__grid">
      <div>
        <DsfrSelect
          :model-value="sourceKind"
          label="D'où vient la valeur"
          label-visible
          :options="sourceOptions"
          @update:model-value="changeSourceKind($event as SourceKind)"
        />
      </div>
      <template v-if="analysisSource">
        <div>
          <DsfrSelect
            :model-value="analysisSource.elementKind"
            label="Type d'élément"
            label-visible
            :options="elementKindOptions"
            @update:model-value="update({ source: { ...analysisSource, elementKind: $event as ElementKind, definitionName: '' } })"
          />
        </div>
        <div>
          <DsfrSelect
            v-if="elementChoices"
            :model-value="analysisSource.definitionName"
            label="Élément de l'analyse"
            label-visible
            :options="elementOptions"
            @update:model-value="update({ source: { ...analysisSource, definitionName: String($event) } })"
          />
          <DsfrInput
            v-else
            :model-value="analysisSource.definitionName"
            label="Nom de l'élément"
            label-visible
            hint="Relation ou champ renseigné : nom libre"
            @update:model-value="update({ source: { ...analysisSource, definitionName: String($event) } })"
          />
        </div>
      </template>
      <div v-else-if="metadataSource">
        <DsfrSelect
          :model-value="metadataSource.key"
          label="Métadonnée"
          label-visible
          :options="metadataOptions"
          @update:model-value="update({ source: { kind: 'dossier_metadata', key: $event as MetadataKey } })"
        />
      </div>
    </div>

    <AssistedTextarea
      :model-value="modelValue.instruction"
      label="Consigne de génération"
      hint="Pour l'agent : format de date, longueur, ton… (facultatif)"
      :rows="2"
      assist-label="Suggérer une consigne"
      :suggest="suggestInstruction"
      @update:model-value="update({ instruction: $event })"
    />

    <ErrorList :errors="issueMessages" />
  </li>
</template>

<style scoped>
.field-row {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.375rem;
  background: var(--background-default-grey);
  list-style: none;
}

.field-row--invalid {
  border-color: var(--border-plain-error);
}

.field-row__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.field-row__name {
  font-weight: 700;
  font-size: 1rem;
}

.field-row__remove {
  margin-left: auto;
}

.field-row__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 0.75rem 1rem;
  align-items: start;
}

.field-row__required {
  align-self: center;
}
</style>
